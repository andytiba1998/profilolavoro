import os
import secrets
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Base paths ---
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
STATIC_DIR = BASE_DIR / "static"

# --- PDF path ---
PDF_PATH = Path(os.getenv("PDF_PATH", str(DATA_DIR / "Codice-civile-Sistematico.pdf")))

# --- LLM configuration ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))

# --- Chunking ---
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# --- Retrieval ---
TOP_K = int(os.getenv("TOP_K", "8"))

# --- Server ---
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# --- Rate limiting ---
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "1000"))

# --- Embedding model (multilingual, supports Italian) ---
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

# --- Collection name in ChromaDB ---
CHROMA_COLLECTION = "codice_civile"

# --- System prompt for LLM ---
SYSTEM_PROMPT = """Sei un assistente giuridico specializzato nel Codice Civile italiano.
Hai accesso al testo integrale del Codice Civile Sistematico (edizione con Relazione Grandi,
giurisprudenza e fonti storiche).

Quando rispondi:
1. Cita sempre il numero dell'articolo (es. "Art. 1453 c.c.")
2. Riporta il testo letterale della norma quando rilevante
3. Se disponibile, includi la Relazione ministeriale e la giurisprudenza
4. Struttura la risposta in sezioni chiare: Norma applicabile / Relazione / Giurisprudenza
5. Aggiungi sempre il disclaimer che non costituisce consulenza legale
6. Rispondi in italiano

Contesto recuperato dal Codice Civile Sistematico:
{context}

Domanda dell'utente:
{question}"""


# --- Security: sensitive data logging filter ---
class SensitiveDataFilter(logging.Filter):
    PATTERNS = ["sk-ant-", "sk-", "Bearer "]

    def filter(self, record):
        msg = str(record.getMessage())
        for pattern in self.PATTERNS:
            if pattern in msg:
                record.msg = "[DATI SENSIBILI RIMOSSI]"
                record.args = ()
        return True


logging.getLogger().addFilter(SensitiveDataFilter())


# --- Security: session token ---
def get_or_create_session_token() -> str:
    """Generate or load a session token for local authentication."""
    token_file = DATA_DIR / ".session_token"
    if token_file.exists():
        return token_file.read_text().strip()

    token = secrets.token_urlsafe(32)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token)

    print(f"\n  Token di accesso: {token}")
    print(f"    Apri http://localhost:{PORT}/?token={token}\n")
    return token


def has_llm_key() -> bool:
    """Check if any LLM API key is configured."""
    if LLM_PROVIDER == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    elif LLM_PROVIDER == "openai":
        return bool(OPENAI_API_KEY)
    return False
