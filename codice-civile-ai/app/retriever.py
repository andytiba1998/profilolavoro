"""
RAG pipeline for Codice Civile Sistematico.

Supports three query modes:
  - SEARCH: semantic search by keyword/phrase
  - ARTICOLO: lookup by article number
  - CASISTICA: legal case analysis with LLM
"""

import re
import asyncio
import logging
from typing import List, Dict, Optional

from sentence_transformers import SentenceTransformer

from app.config import (
    EMBEDDING_MODEL, TOP_K, SYSTEM_PROMPT,
    LLM_PROVIDER, LLM_MODEL, LLM_TIMEOUT,
    ANTHROPIC_API_KEY, OPENAI_API_KEY,
    has_llm_key,
)
from app.models import (
    QueryRequest, QueryResponse, SearchResult, ChunkMetadata, QueryMode,
)
from app.ingest import get_collection

logger = logging.getLogger(__name__)

# Lazy-loaded globals
_embed_model: Optional[SentenceTransformer] = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def _parse_article_number(query: str) -> Optional[str]:
    """Extract article number from queries like 'art. 1453', 'articolo 1453', '1453'."""
    patterns = [
        r"art(?:icolo)?\.?\s*(\d{1,4})",
        r"^(\d{1,4})$",
    ]
    for pat in patterns:
        m = re.search(pat, query.strip(), re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _build_where_filter(
    libro_filter: Optional[str] = None,
    tipo_filter: Optional[str] = None,
) -> Optional[Dict]:
    """Build ChromaDB where filter from request parameters."""
    conditions = []

    if libro_filter:
        conditions.append({"libro": {"$contains": libro_filter}})

    if tipo_filter:
        conditions.append({"tipo_contenuto": tipo_filter})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def search_by_embedding(
    query: str,
    top_k: int = TOP_K,
    where_filter: Optional[Dict] = None,
) -> List[SearchResult]:
    """Perform semantic search using embeddings."""
    collection = get_collection()
    if collection is None or collection.count() == 0:
        return []

    model = _get_embed_model()
    query_embedding = model.encode([query])[0].tolist()

    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        kwargs["where"] = where_filter

    try:
        results = collection.query(**kwargs)
    except Exception as e:
        logger.error(f"Errore ricerca ChromaDB: {e}")
        return []

    search_results = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            meta_raw = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 0
            chunk_id = results["ids"][0][i] if results["ids"] else ""

            # Convert comma-separated articles back to list
            articoli_str = meta_raw.get("articoli", "")
            articoli = [a.strip() for a in articoli_str.split(",") if a.strip()]

            metadata = ChunkMetadata(
                pagina=meta_raw.get("pagina", 0),
                libro=meta_raw.get("libro", ""),
                titolo=meta_raw.get("titolo", ""),
                capo=meta_raw.get("capo", ""),
                articoli=articoli,
                tipo_contenuto=meta_raw.get("tipo_contenuto", "norma"),
            )

            # ChromaDB returns distances; convert to similarity score
            score = max(0.0, 1.0 - distance)

            search_results.append(SearchResult(
                content=doc,
                metadata=metadata,
                score=round(score, 4),
                chunk_id=chunk_id,
            ))

    return search_results


def search_by_article(article_num: str, top_k: int = TOP_K) -> List[SearchResult]:
    """Search for chunks containing a specific article number."""
    collection = get_collection()
    if collection is None or collection.count() == 0:
        return []

    # Use metadata filter to find chunks containing this article
    where_filter = {"articoli": {"$contains": article_num}}

    try:
        results = collection.get(
            where=where_filter,
            include=["documents", "metadatas"],
            limit=top_k,
        )
    except Exception as e:
        logger.error(f"Errore ricerca articolo: {e}")
        return []

    search_results = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"]):
            meta_raw = results["metadatas"][i] if results["metadatas"] else {}
            chunk_id = results["ids"][i] if results["ids"] else ""

            articoli_str = meta_raw.get("articoli", "")
            articoli = [a.strip() for a in articoli_str.split(",") if a.strip()]

            metadata = ChunkMetadata(
                pagina=meta_raw.get("pagina", 0),
                libro=meta_raw.get("libro", ""),
                titolo=meta_raw.get("titolo", ""),
                capo=meta_raw.get("capo", ""),
                articoli=articoli,
                tipo_contenuto=meta_raw.get("tipo_contenuto", "norma"),
            )

            search_results.append(SearchResult(
                content=doc,
                metadata=metadata,
                score=1.0,
                chunk_id=chunk_id,
            ))

    # Sort: norma first, then relazione, then giurisprudenza
    type_order = {"norma": 0, "relazione": 1, "giurisprudenza": 2, "fonte_storica": 3}
    search_results.sort(key=lambda r: type_order.get(r.metadata.tipo_contenuto, 99))

    return search_results


async def _call_llm_api(prompt: str, system: str) -> str:
    """Call the configured LLM API."""
    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = await asyncio.to_thread(
            lambda: client.messages.create(
                model=LLM_MODEL,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        )
        return response.content[0].text

    elif LLM_PROVIDER == "openai":
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
            )
        )
        return response.choices[0].message.content

    raise ValueError(f"Provider LLM non supportato: {LLM_PROVIDER}")


async def query_llm(context: str, question: str) -> str:
    """Call LLM with timeout protection."""
    system_msg = "Sei un assistente giuridico specializzato nel Codice Civile italiano."
    prompt = SYSTEM_PROMPT.format(context=context, question=question)

    try:
        return await asyncio.wait_for(
            _call_llm_api(prompt, system_msg),
            timeout=LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return (
            "Errore: il servizio LLM non ha risposto in tempo. "
            "I risultati della ricerca semantica sono comunque disponibili qui sotto."
        )
    except Exception as e:
        logger.error(f"Errore LLM: {e}")
        return (
            f"Errore nella generazione della risposta: {e}\n\n"
            "I risultati della ricerca semantica sono disponibili qui sotto."
        )


def _format_context(results: List[SearchResult]) -> str:
    """Format search results into context string for the LLM."""
    parts = []
    for i, r in enumerate(results, 1):
        meta = r.metadata
        header_parts = []
        if meta.libro:
            header_parts.append(meta.libro)
        if meta.titolo:
            header_parts.append(meta.titolo)
        if meta.capo:
            header_parts.append(meta.capo)
        if meta.articoli:
            arts = ", ".join(f"Art. {a}" for a in meta.articoli)
            header_parts.append(arts)

        header = " | ".join(header_parts) if header_parts else f"Chunk {i}"
        tipo = meta.tipo_contenuto.upper()
        parts.append(f"[{tipo}] {header} (pag. {meta.pagina}):\n{r.content}")

    return "\n\n---\n\n".join(parts)


async def process_query(request: QueryRequest) -> QueryResponse:
    """Process a user query through the RAG pipeline."""
    question = request.question
    mode = request.mode
    top_k = request.top_k or TOP_K
    where_filter = _build_where_filter(request.libro_filter, request.tipo_filter)

    # Auto-detect article mode
    article_num = _parse_article_number(question)
    if article_num and mode != QueryMode.CASISTICA:
        mode = QueryMode.ARTICOLO

    # Perform search based on mode
    if mode == QueryMode.ARTICOLO and article_num:
        results = search_by_article(article_num, top_k)
        # Also do semantic search as supplement
        semantic = search_by_embedding(
            f"articolo {article_num} codice civile",
            top_k=top_k // 2,
            where_filter=where_filter,
        )
        # Merge, avoiding duplicates
        seen_ids = {r.chunk_id for r in results}
        for s in semantic:
            if s.chunk_id not in seen_ids:
                results.append(s)
    else:
        results = search_by_embedding(question, top_k, where_filter)

    # Generate LLM answer if API key is available
    llm_available = has_llm_key()
    answer = ""

    if llm_available and results:
        context = _format_context(results)
        answer = await query_llm(context, question)
    elif not llm_available and results:
        answer = (
            "Nessuna API key LLM configurata. "
            "Vengono mostrati solo i risultati della ricerca semantica.\n\n"
            "Per ottenere risposte elaborate, configura ANTHROPIC_API_KEY o "
            "OPENAI_API_KEY nel file .env."
        )
    elif not results:
        answer = (
            "Nessun risultato trovato per la tua ricerca. "
            "Verifica che il PDF sia stato indicizzato correttamente."
        )

    return QueryResponse(
        answer=answer,
        results=results,
        mode=mode.value if isinstance(mode, QueryMode) else mode,
        query=question,
        has_llm=llm_available,
    )
