from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any
import os

if os.getenv("ASSIGNMENT_CHAT_ENABLE_LANGSMITH", "FALSE").upper() != "TRUE":
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

from chromadb.errors import NotFoundError
from dotenv import load_dotenv
from langchain.tools import tool
import chromadb

from utils.logger import get_logger


_logs = get_logger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
load_dotenv(SRC_DIR / ".env")
load_dotenv(SRC_DIR / ".secrets")

DATA_DIR = PACKAGE_DIR / "data"
CSV_PATH = DATA_DIR / "toronto_places.csv"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "toronto_places"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
_SEARCH_LOCK = Lock()


def _embed_query(query: str) -> list[float]:
    from utils.clients import get_client

    client = get_client()
    response = client.embeddings.create(
        input=[query],
        model=EMBEDDING_MODEL,
    )
    return response.data[0].embedding


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_collection(name=COLLECTION_NAME)


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": metadata.get("name", ""),
        "category": metadata.get("category", ""),
        "area": metadata.get("area", ""),
        "indoor_outdoor": metadata.get("indoor_outdoor", ""),
        "estimated_cost": metadata.get("estimated_cost", ""),
        "website": metadata.get("website", ""),
    }


@tool
def search_toronto_places(query: str, n_results: int = 3) -> dict[str, Any]:
    """
    Search a local ChromaDB collection of Toronto places and activities using
    semantic similarity. Use this before recommending specific named Toronto
    places or activities. Returns the top relevant entries with structured fields.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return {
            "ok": False,
            "message": "A search query is required.",
            "results": [],
        }

    try:
        top_n = max(1, min(int(n_results), 5))
    except (TypeError, ValueError):
        top_n = 3

    try:
        query_embedding = _embed_query(clean_query)
        with _SEARCH_LOCK:
            collection = get_collection()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_n,
                include=["documents", "metadatas", "distances"],
            )
    except NotFoundError:
        _logs.warning("Chroma collection %s was not found at %s", COLLECTION_NAME, CHROMA_DIR)
        return {
            "ok": False,
            "message": "The Toronto places search index is not available.",
            "results": [],
        }
    except Exception as exc:
        _logs.warning("Toronto places search failed: %s", exc)
        return {
            "ok": False,
            "message": "The Toronto places search service is temporarily unavailable.",
            "results": [],
        }

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    structured_results = []
    for idx, result_id in enumerate(ids):
        metadata = _clean_metadata(metadatas[idx] if idx < len(metadatas) else {})
        structured_results.append(
            {
                "id": result_id,
                "name": metadata["name"],
                "category": metadata["category"],
                "area": metadata["area"],
                "indoor_outdoor": metadata["indoor_outdoor"],
                "estimated_cost": metadata["estimated_cost"],
                "website": metadata["website"],
                "description": documents[idx] if idx < len(documents) else "",
                "distance": distances[idx] if idx < len(distances) else None,
            }
        )

    return {
        "ok": True,
        "query": clean_query,
        "collection": COLLECTION_NAME,
        "results": structured_results,
    }
