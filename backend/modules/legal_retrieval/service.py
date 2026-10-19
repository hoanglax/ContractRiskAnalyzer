from modules.legal_retrieval.database import get_connection
from modules.legal_retrieval.embeddings import embed_query
from modules.legal_retrieval.vector_store import (
    COLLECTION_NAME,
    get_qdrant_client,
)


def search_legal_articles(
    query: str,
    limit: int = 5,
) -> list[dict]:
    if not query or not query.strip():
        raise ValueError("Câu truy vấn không được để trống")

    if not 1 <= limit <= 20:
        raise ValueError("limit phải nằm trong khoảng 1–20")

    vector = embed_query(query)

    client = get_qdrant_client()

    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit,
        with_payload=True,
    )

    hits = response.points

    if not hits:
        return []

    article_ids = [
        hit.payload["article_id"]
        for hit in hits
        if hit.payload and hit.payload.get("article_id")
    ]

    if not article_ids:
        return []

    placeholders = ",".join("?" for _ in article_ids)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
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
            WHERE a.article_id IN ({placeholders})
            """,
            article_ids,
        ).fetchall()

    articles_by_id = {
        row["article_id"]: dict(row)
        for row in rows
    }

    results = []

    for hit in hits:
        article_id = (hit.payload or {}).get("article_id")
        article = articles_by_id.get(article_id)

        if article is None:
            continue

        article["score"] = hit.score
        results.append(article)

    return results


if __name__ == "__main__":
    query = input("Nhập điều khoản cần tìm: ")

    results = search_legal_articles(query)

    for index, item in enumerate(results, start=1):
        print(f"\n--- Kết quả {index} ---")
        print("Văn bản:", item["document_name"])
        print("Trạng thái:", item["document_status"])
        print("Điều:", item["article_number"])
        print("Tiêu đề:", item["title"])
        print("Điểm tương đồng:", item["score"])
        print("Nội dung:", item["full_text"])
        print("Nguồn:", item["source_url"])