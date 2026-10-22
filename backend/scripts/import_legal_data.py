import json
import sqlite3
from pathlib import Path

from modules.legal_retrieval.database import (
    get_connection,
    init_db,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT_DIR / "data" / "legal_corpus" / "legal_corpus.json"


def import_legal_data() -> None:
    with JSON_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    documents = data.get("documents", [])
    articles = data.get("legal_articles", [])

    if not isinstance(documents, list) or not isinstance(articles, list):
        raise ValueError("documents và legal_articles phải là danh sách")

    document_ids = set()

    for doc in documents:
        if not doc.get("doc_id") or not doc.get("name"):
            raise ValueError("Văn bản thiếu doc_id hoặc name")
        if doc["doc_id"] in document_ids:
            raise ValueError(f"Trùng doc_id: {doc['doc_id']}")
        document_ids.add(doc["doc_id"])

    article_ids = set()

    for article in articles:
        required = ("article_id", "doc_id", "article_number", "full_text")
        if any(not article.get(key) for key in required):
            raise ValueError("Điều luật thiếu trường bắt buộc")

        if article["article_id"] in article_ids:
            raise ValueError(f"Trùng article_id: {article['article_id']}")

        article_ids.add(article["article_id"])

        if article["doc_id"] not in document_ids:
            raise ValueError(
                f"Không tìm thấy văn bản của điều luật "
                f"{article['article_id']}"
            )

    init_db()

    try:
        with get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO legal_documents
                    (doc_id, name, document_number, status, source_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    name = excluded.name,
                    document_number = excluded.document_number,
                    status = excluded.status,
                    source_url = excluded.source_url
                """,
                [
                    (
                        doc["doc_id"],
                        doc["name"],
                        doc.get("document_number"),
                        doc.get("status", "CHUA_XAC_MINH"),
                        doc.get("source_url"),
                    )
                    for doc in documents
                ],
            )

            conn.executemany(
                """
                INSERT INTO legal_articles
                    (article_id, doc_id, article_number,
                     title, full_text, source_url)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    doc_id = excluded.doc_id,
                    article_number = excluded.article_number,
                    title = excluded.title,
                    full_text = excluded.full_text,
                    source_url = excluded.source_url
                """,
                [
                    (
                        article["article_id"],
                        article["doc_id"],
                        article["article_number"],
                        article.get("title"),
                        article["full_text"],
                        article.get("source_url"),
                    )
                    for article in articles
                ],
            )

    except sqlite3.Error:
        raise

    print(f"Đã nhập/cập nhật {len(documents)} văn bản.")
    print(f"Đã nhập/cập nhật {len(articles)} điều luật.")


if __name__ == "__main__":
    import_legal_data()