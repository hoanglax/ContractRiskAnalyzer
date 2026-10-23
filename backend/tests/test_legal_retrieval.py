from unittest.mock import patch

import pytest

from modules.legal_retrieval.service import search_legal_articles


def test_empty_query_is_rejected():
    with pytest.raises(ValueError):
        search_legal_articles("   ")


def test_invalid_limit_is_rejected():
    with pytest.raises(ValueError):
        search_legal_articles("Hợp đồng thuê nhà", limit=0)


def test_search_returns_sqlite_source_in_qdrant_order():
    fake_hits = [
        type(
            "Hit",
            (),
            {
                "payload": {"article_id": "ARTICLE_2"},
                "score": 0.91,
            },
        )(),
        type(
            "Hit",
            (),
            {
                "payload": {"article_id": "ARTICLE_1"},
                "score": 0.85,
            },
        )(),
    ]

    fake_response = type("Response", (), {"points": fake_hits})()

    fake_rows = [
        {
            "article_id": "ARTICLE_1",
            "doc_id": "DOC_1",
            "article_number": "Điều 1",
            "title": "Điều thứ nhất",
            "full_text": "Nội dung thứ nhất",
            "source_url": "https://example.com/1",
            "document_name": "Văn bản mẫu",
            "document_status": "DA_XAC_MINH",
        },
        {
            "article_id": "ARTICLE_2",
            "doc_id": "DOC_1",
            "article_number": "Điều 2",
            "title": "Điều thứ hai",
            "full_text": "Nội dung thứ hai",
            "source_url": "https://example.com/2",
            "document_name": "Văn bản mẫu",
            "document_status": "DA_XAC_MINH",
        },
    ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):
            assert params == ["ARTICLE_2", "ARTICLE_1"]

            class FakeCursor:
                def fetchall(self):
                    return fake_rows

            return FakeCursor()

    with (
        patch(
            "modules.legal_retrieval.service.embed_query",
            return_value=[0.0] * 768,
        ),
        patch(
            "modules.legal_retrieval.service.get_qdrant_client"
        ) as mock_client,
        patch(
            "modules.legal_retrieval.service.get_connection",
            return_value=FakeConnection(),
        ),
    ):
        mock_client.return_value.query_points.return_value = fake_response

        results = search_legal_articles("Điều khoản thuê nhà")

    assert [item["article_id"] for item in results] == [
        "ARTICLE_2",
        "ARTICLE_1",
    ]
    assert results[0]["score"] == 0.91
    assert results[0]["full_text"] == "Nội dung thứ hai"