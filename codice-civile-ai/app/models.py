import re
from pydantic import BaseModel, field_validator
from typing import Optional, List
from enum import Enum


class QueryMode(str, Enum):
    SEARCH = "search"
    CASISTICA = "casistica"
    ARTICOLO = "articolo"


class QueryRequest(BaseModel):
    question: str
    mode: QueryMode = QueryMode.SEARCH
    libro_filter: Optional[str] = None
    tipo_filter: Optional[str] = None
    top_k: Optional[int] = None

    @field_validator("question")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        v = re.sub(r"[\x00-\x1f\x7f]", "", v)
        if len(v) > 1000:
            raise ValueError("Query troppo lunga (max 1000 caratteri)")
        if len(v.strip()) < 3:
            raise ValueError("Query troppo corta (min 3 caratteri)")
        return v.strip()

    @field_validator("libro_filter")
    @classmethod
    def validate_libro(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        allowed = [
            "LIBRO PRIMO", "LIBRO SECONDO", "LIBRO TERZO",
            "LIBRO QUARTO", "LIBRO QUINTO", "LIBRO SESTO",
        ]
        if v not in allowed:
            raise ValueError("Valore non valido per 'libro'")
        return v

    @field_validator("tipo_filter")
    @classmethod
    def validate_tipo(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        allowed = ["norma", "relazione", "giurisprudenza", "fonte_storica"]
        if v not in allowed:
            raise ValueError("Valore non valido per 'tipo_contenuto'")
        return v

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        return max(1, min(v, 20))


class ChunkMetadata(BaseModel):
    pagina: int = 0
    libro: str = ""
    titolo: str = ""
    capo: str = ""
    articoli: List[str] = []
    tipo_contenuto: str = "norma"


class SearchResult(BaseModel):
    content: str
    metadata: ChunkMetadata
    score: float = 0.0
    chunk_id: str = ""


class QueryResponse(BaseModel):
    answer: str
    results: List[SearchResult]
    mode: str
    query: str
    has_llm: bool


class IngestStatus(BaseModel):
    status: str = "not_started"  # not_started | in_progress | completed | error
    progress: float = 0.0
    total_pages: int = 0
    processed_pages: int = 0
    total_chunks: int = 0
    message: str = ""
    error: Optional[str] = None
