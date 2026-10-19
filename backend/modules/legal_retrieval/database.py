from pathlib import Path
import sqlite3

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS legal_documents (
                doc_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                document_number TEXT,
                status TEXT NOT NULL,
                source_url TEXT
            );

            CREATE TABLE IF NOT EXISTS legal_articles (
                article_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                article_number TEXT NOT NULL,
                title TEXT,
                full_text TEXT NOT NULL,
                source_url TEXT,
                FOREIGN KEY (doc_id)
                    REFERENCES legal_documents(doc_id)
            );

            CREATE INDEX IF NOT EXISTS idx_articles_doc_id
                ON legal_articles(doc_id);
            """
        )


if __name__ == "__main__":
    init_db()
    print(f"SQLite initialized: {DB_PATH}")