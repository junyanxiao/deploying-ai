from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
import chromadb
import pandas as pd
import os
import shutil

from utils.logger import get_logger


PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
load_dotenv(SRC_DIR / ".env")
load_dotenv(SRC_DIR / ".secrets")

DATA_DIR = PACKAGE_DIR / "data"
CSV_PATH = DATA_DIR / "toronto_places.csv"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "toronto_places"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
REQUIRED_COLUMNS = [
    "id",
    "name",
    "category",
    "description",
    "area",
    "indoor_outdoor",
    "estimated_cost",
    "website",
]

_logs = get_logger(__name__)


def build_search_document(row: pd.Series) -> str:
    return "\n".join(
        [
            f"Name: {row['name']}",
            f"Category: {row['category']}",
            f"Description: {row['description']}",
            f"Area: {row['area']}",
            f"Setting: {row['indoor_outdoor']}",
            f"Estimated cost: {row['estimated_cost']}",
        ]
    )


def _batched(items: list[str], batch_size: int = 64) -> Iterable[list[str]]:
    for idx in range(0, len(items), batch_size):
        yield items[idx : idx + batch_size]


def _load_openai_client():
    from utils.clients import get_client

    return get_client()


def _embed_documents(documents: list[str]) -> list[list[float]]:
    client = _load_openai_client()
    embeddings = []
    for batch in _batched(documents):
        response = client.embeddings.create(
            input=batch,
            model=EMBEDDING_MODEL,
        )
        embeddings.extend([item.embedding for item in sorted(response.data, key=lambda item: item.index)])
    return embeddings


def validate_dataframe(df: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if df["id"].duplicated().any():
        duplicates = df.loc[df["id"].duplicated(), "id"].tolist()
        raise ValueError(f"Duplicate ids are not allowed: {duplicates}")


def build_collection() -> int:
    df = pd.read_csv(CSV_PATH).fillna("")
    validate_dataframe(df)

    documents = [build_search_document(row) for _, row in df.iterrows()]
    ids = df["id"].astype(str).tolist()
    metadatas = [
        {
            "name": row["name"],
            "category": row["category"],
            "area": row["area"],
            "indoor_outdoor": row["indoor_outdoor"],
            "estimated_cost": row["estimated_cost"],
            "website": row["website"],
        }
        for _, row in df.iterrows()
    ]

    _logs.info("Embedding %s Toronto place records with %s", len(documents), EMBEDDING_MODEL)
    embeddings = _embed_documents(documents)

    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = chroma_client.create_collection(name=COLLECTION_NAME)
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    return len(ids)


def main() -> None:
    count = build_collection()
    message = (
        f"Built ChromaDB collection '{COLLECTION_NAME}' with {count} records "
        f"at {CHROMA_DIR} using {EMBEDDING_MODEL}."
    )
    _logs.info(message)
    print(message)


if __name__ == "__main__":
    main()
