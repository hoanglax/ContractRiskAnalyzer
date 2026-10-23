"""Statute knowledge base: articles + khoản-level chunks + FTS5 lexical index, in one SQLite file.

Storage choice (2026-10): SQLite + FTS5 (+ a row-aligned numpy matrix for vectors, added by the
embedder step). The corpus is a few thousand chunks (~40 MB of vectors), so brute force is instant, it
runs on any laptop with nothing to deploy, and the Vietnamese-specific work (tokenisation, khoản
chunking, verbatim citations) is identical in any store. `Retriever` (retriever.py) is the seam: a
Qdrant or Postgres implementation can replace this one without touching callers.

Offsets: `articles.char_start/char_end` index into `clean(file text)`, so a citation can be checked
as a verbatim slice of the source (`verify`).

    python -m application.modules.legal_retrieval.kb build [--corpus DIR ...] [--db PATH]
    python -m application.modules.legal_retrieval.kb stats
    python -m application.modules.legal_retrieval.kb search "bên thuê cho thuê lại nhà ở" -k 5
"""
import argparse
import os
import re
import sqlite3
import unicodedata
from pathlib import Path

from application.modules.ingestion.structure import segment
from application.modules.ingestion.text import clean
from application.modules.legal_retrieval.chunk import khoan_split
from application.modules.legal_retrieval.retriever import Hit

BACKEND = Path(__file__).resolve().parents[3]
REPO = BACKEND.parent
DEFAULT_DB = BACKEND / "cache" / "legal_kb.db"
DEFAULT_CORPUS = [REPO / "data" / "legal_corpus", REPO / "data" / "test" / "kb"]
SKIP = {"nd96_2024_ma_template"}            # superseded placeholder, by file stem


def _pyvi():
    try:
        from pyvi import ViTokenizer
        return ViTokenizer.tokenize
    except ImportError:
        return None


TOKENIZER = os.environ.get("KB_TOKENIZER", "pairs")        # pairs | pyvi | both


def tokenize(text: str) -> list[str]:
    """FTS terms. "pairs": lowercase NFC syllables plus adjacent-syllable pairs ("cho_thuê"), no
    dependency. "pyvi": syllables plus pyvi word tokens ("hợp_đồng"). "both": the union. The index and
    the query must use the same setting, so changing it needs a rebuild."""
    syl = re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())
    out = list(syl)
    if TOKENIZER in ("pairs", "both"):
        out += [f"{a}_{b}" for a, b in zip(syl, syl[1:])]
    if TOKENIZER in ("pyvi", "both"):
        seg = _pyvi()
        if seg is None:
            raise RuntimeError("KB_TOKENIZER=pyvi needs `pip install pyvi`")
        out += [w for w in re.findall(r"\w+", seg(unicodedata.normalize("NFC", text).lower())) if "_" in w]
    return out


SCHEMA = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY, law TEXT, dieu_no INTEGER, heading TEXT, text TEXT,
    char_start INTEGER, char_end INTEGER);
CREATE TABLE chunks (id INTEGER PRIMARY KEY, article_id INTEGER, ref TEXT, text TEXT);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    fts_text, tokenize="unicode61 remove_diacritics 2 tokenchars '_'");
"""


def _split_article(text: str, heading: str) -> tuple[str, str]:
    """-> (heading, body). A standalone 'Điều N' marker keeps its title on the second line."""
    lines = text.split("\n")
    drop = 1
    if lines[0].strip() != heading and len(lines) > 1 and lines[1].strip() in heading:
        drop = 2
    return heading, "\n".join(lines[drop:])


def build(corpus: list[Path] | None = None, db_path: Path = DEFAULT_DB) -> dict:
    files = {}
    for d in corpus or DEFAULT_CORPUS:                  # an earlier directory wins on a repeated name
        for f in sorted(Path(d).glob("*.txt")):
            if f.stem not in SKIP:
                files.setdefault(f.stem, f)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        n_art = n_chunk = 0
        per_law = {}

        for law, f in files.items():
            text = clean(f.read_text(encoding="utf-8", errors="replace"))
            st, dg = segment(text)
            if not st.clauses:
                raise ValueError(f"{f.name}: no Điều found ({', '.join(dg.reasons)})")

            for c in st.clauses:
                m = re.match(r"Điều\s+(\d+)\s*$", c.label)
                art_text = text[c.char_start:c.char_end]
                heading, body = _split_article(art_text, c.heading)
                con.execute(
                    "INSERT INTO articles VALUES (?,?,?,?,?,?,?)",
                    (n_art, law, int(m.group(1)) if m else None,
                     heading, art_text, c.char_start, c.char_end),
                )

                for ref, chunk in khoan_split(heading, body):
                    con.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?)",
                        (n_chunk, n_art, ref, chunk),
                    )
                    con.execute(
                        "INSERT INTO chunks_fts(rowid, fts_text) VALUES (?,?)",
                        (n_chunk, " ".join(tokenize(chunk))),
                    )
                    n_chunk += 1

                n_art += 1

            per_law[law] = len(st.clauses)

        con.commit()
        return {
            "articles": n_art,
            "chunks": n_chunk,
            "per_law": per_law,
            "db": str(db_path),
        }
    finally:
        con.close()



def hits_for(con: sqlite3.Connection, scored: list[tuple[int, float]]) -> list[Hit]:
    """[(chunk_id, score)] -> Hits, in the given order."""
    out = []
    for cid, score in scored:
        r = con.execute("SELECT c.article_id, a.law, a.dieu_no, c.ref, c.text FROM chunks c "
                        "JOIN articles a ON a.id = c.article_id WHERE c.id = ?", (cid,)).fetchone()
        out.append(Hit(cid, r[0], r[1], r[2], r[3], score, r[4]))
    return out



class LexicalRetriever:
    """BM25 over khoan chunks."""

    def __init__(self, db_path: Path = DEFAULT_DB):
        self.con = sqlite3.connect(db_path)

    def search(self, query: str, k: int = 5, law: str | None = None) -> list[Hit]:
        terms = tokenize(query)
        if not terms:
            return []

        match = " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))
        rows = self.con.execute(
            """SELECT c.id, c.article_id, a.law, a.dieu_no, c.ref, -bm25(chunks_fts), c.text
               FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
               JOIN articles a ON a.id = c.article_id
               WHERE chunks_fts MATCH ? AND (? IS NULL OR a.law = ?)
               ORDER BY rank LIMIT ?""",
            (match, law, law, k),
        ).fetchall()
        return [Hit(*r) for r in rows]

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


def verify(
    db_path: Path = DEFAULT_DB,
    corpus: list[Path] | None = None,
) -> list[str]:
    """Every article must equal its slice of the cleaned source file.
    Returns the problems found.
    """
    files = {}
    for d in corpus or DEFAULT_CORPUS:
        for f in sorted(Path(d).glob("*.txt")):
            files.setdefault(f.stem, f)

    texts, bad = {}, []

    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT law, char_start, char_end, text FROM articles"
        ).fetchall()

        for law, s, e, t in rows:
            if law not in texts:
                texts[law] = clean(
                    files[law].read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                )
            if texts[law][s:e] != t:
                bad.append(f"{law}[{s}:{e}]")
    finally:
        con.close()

    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "stats", "search"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--corpus", nargs="*", type=Path)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    a = ap.parse_args()
    if a.cmd == "build":
        r = build(a.corpus, a.db)
        print(f"{r['articles']} articles, {r['chunks']} chunks -> {r['db']}")
        for law, n in r["per_law"].items():
            print(f"  {law:42} {n:4}")
        bad = verify(a.db, a.corpus)
        print("verbatim check:", "ok" if not bad else f"{len(bad)} mismatches, first {bad[:3]}")
        return
    if not a.db.exists():
        raise SystemExit("no index; run: python -m application.modules.legal_retrieval.kb build")
    if a.cmd == "stats":
        con = sqlite3.connect(a.db)
        for law, n_art, n_ch in con.execute(
                "SELECT a.law, count(DISTINCT a.id), count(c.id) FROM articles a "
                "JOIN chunks c ON c.article_id = a.id GROUP BY a.law ORDER BY a.law"):
            print(f"  {law:42} điều={n_art:4} chunks={n_ch:5}")
        return
    for h in LexicalRetriever(a.db).search(a.query, a.k):
        print(f"  {h.score:7.2f}  {h.law} Điều {h.dieu_no} [{h.ref or '-'}]  {h.text.splitlines()[-1][:90]}")


if __name__ == "__main__":
    main()
