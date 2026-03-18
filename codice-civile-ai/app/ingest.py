"""
PDF ingestion and ChromaDB indexing for Codice Civile Sistematico.

Extracts text from the PDF, identifies structural metadata (Libro, Titolo, Capo,
article numbers, content type), creates intelligent chunks, and indexes them
into a persistent ChromaDB vector store.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional

import pdfplumber
import chromadb
from sentence_transformers import SentenceTransformer

from app.config import (
    PDF_PATH, CHROMA_DIR, CHUNK_SIZE, CHUNK_OVERLAP,
    EMBEDDING_MODEL, CHROMA_COLLECTION, DATA_DIR,
)
from app.models import IngestStatus

logger = logging.getLogger(__name__)

# Global status object for progress tracking
_ingest_status = IngestStatus()


def get_ingest_status() -> IngestStatus:
    return _ingest_status


def safe_pdf_path(pdf_path: str) -> str:
    """Prevent path traversal attacks."""
    base_dir = os.path.abspath(str(DATA_DIR))
    resolved = os.path.abspath(pdf_path)
    if not resolved.startswith(base_dir):
        raise ValueError(f"Path non autorizzato: {pdf_path}")
    if not resolved.endswith(".pdf"):
        raise ValueError("Il file deve essere un PDF")
    return resolved


# --- Structural metadata extraction patterns ---

LIBRO_PATTERN = re.compile(
    r"LIBRO\s+(PRIMO|SECONDO|TERZO|QUARTO|QUINTO|SESTO)\b"
    r"(\s*[-–—]\s*.+)?",
    re.IGNORECASE,
)

TITOLO_PATTERN = re.compile(
    r"(?:^|\n)\s*Titolo\s+([IVXLCDM]+(?:\s*-?\s*bis)?)"
    r"(\s*[-–—]\s*.+)?",
    re.IGNORECASE,
)

CAPO_PATTERN = re.compile(
    r"(?:^|\n)\s*Capo\s+([IVXLCDM]+(?:\s*-?\s*bis)?)"
    r"(\s*[-–—]\s*.+)?",
    re.IGNORECASE,
)

# Article patterns: "1453." at start of line, or "Art. 1453"
ARTICOLO_LINE_PATTERN = re.compile(r"(?:^|\n)\s*(\d{1,4})\s*\.")
ARTICOLO_ART_PATTERN = re.compile(r"Art\.?\s*(\d{1,4})", re.IGNORECASE)

# Content type detection patterns
RELAZIONE_PATTERN = re.compile(r"RELAZIONE|Relazione del Ministro|Relazione Grandi", re.IGNORECASE)
GIURISPRUDENZA_PATTERN = re.compile(
    r"Cass\.\s|Trib\.\s|App\.\s|Corte\s+Cost\.|sentenz[ae]|"
    r"Sez\.\s+Un\.|decreto\s+\d|ordinanz[ae]",
    re.IGNORECASE,
)
FONTE_STORICA_PATTERN = re.compile(
    r"[Cc]odice\s+civile\s+del\s+1865|"
    r"[Cc]odice\s+del\s+commercio\s+del\s+1882|"
    r"[Cc]odice\s+del\s+commercio\s+del\s+1889|"
    r"codice\s+abrogato",
    re.IGNORECASE,
)


def detect_content_type(text: str) -> str:
    """Determine the content type of a text chunk."""
    relazione_count = len(RELAZIONE_PATTERN.findall(text))
    giuris_count = len(GIURISPRUDENZA_PATTERN.findall(text))
    storica_count = len(FONTE_STORICA_PATTERN.findall(text))

    scores = {
        "relazione": relazione_count * 3,
        "giurisprudenza": giuris_count,
        "fonte_storica": storica_count * 2,
        "norma": 1,  # default
    }

    best = max(scores, key=scores.get)
    if scores[best] <= 1 and best != "norma":
        return "norma"
    return best


def extract_articles(text: str) -> List[str]:
    """Extract article numbers from text."""
    articles = set()
    for m in ARTICOLO_LINE_PATTERN.finditer(text):
        num = m.group(1)
        if 1 <= int(num) <= 9999:
            articles.add(num)
    for m in ARTICOLO_ART_PATTERN.finditer(text):
        num = m.group(1)
        if 1 <= int(num) <= 9999:
            articles.add(num)
    return sorted(articles, key=lambda x: int(x))


def smart_chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split text into chunks, trying to respect article boundaries.
    Uses article number patterns as natural separators.
    """
    if not text.strip():
        return []

    # Try to split on article boundaries first
    article_boundary = re.compile(r"(?=(?:^|\n)\s*\d{1,4}\s*\.)")
    segments = article_boundary.split(text)
    segments = [s for s in segments if s.strip()]

    if not segments:
        segments = [text]

    chunks = []
    current_chunk = ""

    for segment in segments:
        if len(current_chunk) + len(segment) <= chunk_size:
            current_chunk += segment
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # If a single segment is larger than chunk_size, split it further
            if len(segment) > chunk_size:
                words = segment.split()
                sub_chunk = ""
                for word in words:
                    if len(sub_chunk) + len(word) + 1 <= chunk_size:
                        sub_chunk += (" " if sub_chunk else "") + word
                    else:
                        if sub_chunk.strip():
                            chunks.append(sub_chunk.strip())
                        sub_chunk = word
                current_chunk = sub_chunk
            else:
                current_chunk = segment

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Add overlap between chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            overlapped.append(prev_tail + " " + chunks[i])
        chunks = overlapped

    return chunks


def extract_pdf_pages(pdf_path: str) -> List[Dict]:
    """Extract text and metadata from each page of the PDF."""
    global _ingest_status

    safe_path = safe_pdf_path(pdf_path)
    pages_data = []

    with pdfplumber.open(safe_path) as pdf:
        total = len(pdf.pages)
        _ingest_status.total_pages = total
        _ingest_status.status = "in_progress"
        _ingest_status.message = f"Estrazione testo da {total} pagine..."

        current_libro = ""
        current_titolo = ""
        current_capo = ""

        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                _ingest_status.processed_pages = i + 1
                _ingest_status.progress = ((i + 1) / total) * 50  # 0-50% for extraction
                continue

            # Update structural context
            libro_match = LIBRO_PATTERN.search(text)
            if libro_match:
                current_libro = libro_match.group(0).strip()

            titolo_match = TITOLO_PATTERN.search(text)
            if titolo_match:
                current_titolo = titolo_match.group(0).strip()

            capo_match = CAPO_PATTERN.search(text)
            if capo_match:
                current_capo = capo_match.group(0).strip()

            pages_data.append({
                "page_num": i + 1,
                "text": text,
                "libro": current_libro,
                "titolo": current_titolo,
                "capo": current_capo,
            })

            _ingest_status.processed_pages = i + 1
            _ingest_status.progress = ((i + 1) / total) * 50

            if (i + 1) % 100 == 0:
                logger.info(f"Estratte {i + 1}/{total} pagine")

    return pages_data


def create_chunks(pages_data: List[Dict]) -> List[Dict]:
    """Create text chunks with metadata from extracted pages."""
    global _ingest_status

    all_chunks = []
    total_pages = len(pages_data)

    for idx, page in enumerate(pages_data):
        text = page["text"]
        chunks = smart_chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)

        for chunk_idx, chunk_text in enumerate(chunks):
            articles = extract_articles(chunk_text)
            content_type = detect_content_type(chunk_text)

            chunk = {
                "id": f"p{page['page_num']}_c{chunk_idx}",
                "text": chunk_text,
                "metadata": {
                    "pagina": page["page_num"],
                    "libro": page["libro"],
                    "titolo": page["titolo"],
                    "capo": page["capo"],
                    "articoli": ",".join(articles),  # ChromaDB stores strings
                    "tipo_contenuto": content_type,
                },
            }
            all_chunks.append(chunk)

        _ingest_status.progress = 50 + ((idx + 1) / total_pages) * 30  # 50-80%

    _ingest_status.total_chunks = len(all_chunks)
    _ingest_status.message = f"Creati {len(all_chunks)} chunk di testo"
    logger.info(f"Creati {len(all_chunks)} chunk da {total_pages} pagine")
    return all_chunks


def index_chunks(chunks: List[Dict]) -> chromadb.Collection:
    """Index chunks into ChromaDB with sentence-transformer embeddings."""
    global _ingest_status

    _ingest_status.message = "Caricamento modello di embedding..."
    _ingest_status.progress = 80

    model = SentenceTransformer(EMBEDDING_MODEL)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Delete existing collection if present (re-index)
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except ValueError:
        pass

    collection = client.create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    _ingest_status.message = "Indicizzazione in corso..."

    # Process in batches to manage memory
    batch_size = 100
    total = len(chunks)

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = chunks[start:end]

        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        _ingest_status.progress = 80 + ((end / total) * 20)  # 80-100%
        _ingest_status.message = f"Indicizzati {end}/{total} chunk..."

        if end % 500 == 0 or end == total:
            logger.info(f"Indicizzati {end}/{total} chunk")

    return collection


def is_indexed() -> bool:
    """Check if the vector store already exists with data."""
    if not CHROMA_DIR.exists():
        return False
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        collection = client.get_collection(CHROMA_COLLECTION)
        return collection.count() > 0
    except Exception:
        return False


def run_ingestion(force: bool = False) -> IngestStatus:
    """Run the full ingestion pipeline."""
    global _ingest_status

    if not force and is_indexed():
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        collection = client.get_collection(CHROMA_COLLECTION)
        count = collection.count()
        _ingest_status = IngestStatus(
            status="completed",
            progress=100,
            total_chunks=count,
            message=f"Vector store caricato: {count} chunk indicizzati",
        )
        logger.info(f"Vector store esistente caricato con {count} chunk")
        return _ingest_status

    pdf_path = str(PDF_PATH)
    if not Path(pdf_path).exists():
        _ingest_status = IngestStatus(
            status="error",
            error=f"File PDF non trovato: {pdf_path}",
            message="Posiziona il file Codice-civile-Sistematico.pdf nella cartella data/",
        )
        return _ingest_status

    try:
        _ingest_status = IngestStatus(status="in_progress", message="Avvio indicizzazione...")

        logger.info("Avvio estrazione testo dal PDF...")
        pages = extract_pdf_pages(pdf_path)

        logger.info("Creazione chunk di testo...")
        chunks = create_chunks(pages)

        logger.info("Indicizzazione nel vector store...")
        index_chunks(chunks)

        _ingest_status.status = "completed"
        _ingest_status.progress = 100
        _ingest_status.message = (
            f"Indicizzazione completata: {_ingest_status.total_chunks} chunk "
            f"da {_ingest_status.total_pages} pagine"
        )
        logger.info(_ingest_status.message)

    except Exception as e:
        logger.exception("Errore durante l'indicizzazione")
        _ingest_status.status = "error"
        _ingest_status.error = str(e)
        _ingest_status.message = f"Errore: {e}"

    return _ingest_status


def get_collection() -> Optional[chromadb.Collection]:
    """Get the ChromaDB collection if it exists."""
    if not CHROMA_DIR.exists():
        return None
    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return client.get_collection(CHROMA_COLLECTION)
    except Exception:
        return None
