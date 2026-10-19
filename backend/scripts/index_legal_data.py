import uuid

from qdrant_client import models

from modules.legal_retrieval.database import get_connection
from modules.legal_retrieval.embeddings import embed_passages
from modules.legal_retrieval.vector_store import (
    COLLECTION_NAME,
    ensure_collection,
    get_qdrant_client,
)

POINT_NAMESPACE = uuid.UUID("c6c48dce-a822-4ed5-a1c7-48c6a8eb8db7")
BATCH_SIZE = 32


def point_id_for(article_id: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, article_id))


def index_legal_data() -> None:
    ensure_collection()
    client = get_qdrant_client()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.article_id,
                a.doc_id,
                a.article_number,
                a.title,
                a.full_text,
                a.source_url,
                d.name AS document_name,
                d.status AS document_status
            FROM legal_articles AS a
            JOIN legal_documents AS d ON d.doc_id = a.doc_id
            ORDER BY a.article_id
            """
        ).fetchall()

    if not rows:
        print("Chưa có điều luật trong SQLite.")
        return

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        texts = [
            " ".join(
                part for part in (
                    row["document_name"],
                    row["article_number"],
                    row["title"],
                    row["full_text"],
                )
                if part
            )
            for row in batch
        ]

        vectors = embed_passages(texts)

        points = []

        for row, vector in zip(batch, vectors):
            points.append(
                models.PointStruct(
                    id=point_id_for(row["article_id"]),
                    vector=vector,
                    payload={
                        "article_id": row["article_id"],
                        "doc_id": row["doc_id"],
                        "article_number": row["article_number"],
                        "document_name": row["document_name"],
                        "document_status": row["document_status"],
                    },
                )
            )

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )

        print(
            f"Đã lập chỉ mục "
            f"{min(start + len(batch), len(rows))}/{len(rows)} điều luật."
        )

    print("Hoàn tất lập chỉ mục Qdrant.")


if __name__ == "__main__":
    index_legal_data()