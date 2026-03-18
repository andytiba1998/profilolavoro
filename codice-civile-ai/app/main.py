"""
FastAPI entry point for the Codice Civile Sistematico RAG application.

Includes security middleware (localhost-only, token auth, rate limiting,
security headers, CORS), static file serving, and API endpoints.
"""

import os
import sys
import logging
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Ensure the parent dir is in sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import (
    HOST, PORT, STATIC_DIR, RATE_LIMIT_PER_MINUTE,
    get_or_create_session_token, has_llm_key,
)
from app.models import QueryRequest, QueryResponse, IngestStatus
from app.ingest import run_ingestion, get_ingest_status, is_indexed
from app.retriever import process_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- App setup ---
app = FastAPI(title="Codice Civile Sistematico AI", docs_url=None, redoc_url=None)

# --- Rate limiter ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Session token ---
SESSION_TOKEN = get_or_create_session_token()

# --- CORS: only allow localhost ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-Token"],
)


# --- Security middleware: localhost-only + token auth ---
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 1. Only allow localhost connections
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return JSONResponse(status_code=403, content={"error": "Accesso negato"})

    # 2. Token verification (skip for static files and root page)
    path = request.url.path
    if path.startswith("/api/"):
        token = (
            request.query_params.get("token")
            or request.headers.get("X-Session-Token")
        )
        if token != SESSION_TOKEN:
            return JSONResponse(status_code=401, content={"error": "Token non valido"})

    response = await call_next(request)

    # 3. Security headers on every response
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    return response


# --- Static files ---
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Routes ---

@app.get("/")
async def root(request: Request):
    """Serve the main HTML page."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/status")
async def status(request: Request):
    """Return current ingestion status and system info."""
    ingest = get_ingest_status()
    return {
        "ingest": ingest.model_dump(),
        "has_llm": has_llm_key(),
        "indexed": is_indexed(),
        "token": SESSION_TOKEN,
    }


@app.post("/api/query")
@limiter.limit(f"{RATE_LIMIT_PER_MINUTE}/minute")
async def query_endpoint(request: Request, body: QueryRequest):
    """Process a search/analysis query."""
    if not is_indexed():
        return JSONResponse(
            status_code=503,
            content={"error": "Il vector store non e' ancora pronto. Attendi il completamento dell'indicizzazione."},
        )

    response = await process_query(body)
    return response.model_dump()


@app.post("/api/ingest")
@limiter.limit("2/hour")
async def ingest_endpoint(request: Request):
    """Trigger PDF ingestion (re-indexing)."""
    def _run():
        run_ingestion(force=True)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"message": "Indicizzazione avviata in background", "status": "in_progress"}


@app.get("/api/ingest/status")
async def ingest_status_endpoint(request: Request):
    """Get current ingestion progress."""
    return get_ingest_status().model_dump()


# --- Startup: auto-index on first run ---
@app.on_event("startup")
async def startup_event():
    logger.info("Avvio applicazione Codice Civile Sistematico AI")
    logger.info(f"Server in ascolto su http://{HOST}:{PORT}")
    logger.info(f"LLM configurato: {'Si' if has_llm_key() else 'No (solo ricerca semantica)'}")

    if not is_indexed():
        logger.info("Vector store non trovato. Avvio indicizzazione automatica...")

        def _auto_ingest():
            run_ingestion(force=False)

        thread = threading.Thread(target=_auto_ingest, daemon=True)
        thread.start()
    else:
        # Load status from existing index
        run_ingestion(force=False)
        logger.info("Vector store esistente caricato.")


# --- Main entry point ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
