"""M4: the legal basis of each finding, picked from statute passages the code put in front of the model.

    from application.modules.legal_basis.basis import attach
    out = attach(findings)    # {"items": one per finding, same order, "warnings": about the run}

Candidates (each a khoản-level chunk of the KB, given an id C1, C2 ...):
  1. the articles the finding's taxonomy row cites (resolved to KB ids by taxonomy.build); a citation that names a
     law but no article is searched within that law; one whose law is not in the KB is skipped with a warning;
  2. retrieval over the whole KB with a query built from the finding (issue + quote, or issue + risk name for a
     missing term). Taxonomy candidates come first; a passage found both ways is listed once.
The model (task "legal_pick") answers with candidate ids only (M6 explains them; a "why" here cost ~3 s a call). An id that is not a candidate is
dropped with a warning; the text of a LegalBasis always comes from the KB. An empty list means no basis was
found, and is shown as such: an article number is never written by the model.
"""
from __future__ import annotations

import functools
import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass

from application.adapters import llm
from application.modules.detection.finding import Finding
from application.modules.legal_retrieval.kb import DEFAULT_DB, LexicalRetriever
from application.modules.legal_retrieval.retriever import Hit, Retriever
from application.modules.taxonomy import taxonomy

log = logging.getLogger(__name__)
RETRIEVED = 6           # passages from whole-KB retrieval per finding
PER_ARTICLE = 4         # passages kept from one cited article (its khoản best matching the finding first)
PER_LAW = 3             # passages for a citation that names a law but no article
MAX_CHARS = 1200        # of one passage, in the prompt only; the LegalBasis keeps the full text
MAX_PICKS = 3
NOT_STATUTE = {"nd96_2024_fuluc2_hop_dong_thue_nha_o"}     # a model contract in the KB, not a rule to cite
DENSE_TAG = "80m"       # hybrid default: BM25 + this embedder (docs/note/legal-retrieval-experiments.md)

PROMPT = """Bạn là luật sư Việt Nam. Dưới đây là một rủi ro phát hiện trong hợp đồng thuê nhà ở, và các đoạn văn bản pháp luật ứng viên.
Hãy chọn những đoạn là căn cứ pháp lý trực tiếp cho rủi ro này (quy định bị vi phạm, giới hạn bị vượt, hoặc quyền/nghĩa vụ liên quan). Tối đa {max_picks} đoạn, phù hợp nhất trước. Không đoạn nào phù hợp thì trả danh sách rỗng; không được tự viết điều luật ngoài danh sách.

RỦI RO: [{code}] {name}
Vấn đề: {issue}
{quote_line}
CÁC ĐOẠN ỨNG VIÊN:
{candidates}

Chỉ trả lời bằng JSON, chỉ gồm mã đoạn, không giải thích:
{{"basis": ["C1", "C4"]}}"""


# KB law id -> how a reader names it; an id missing here is shown as is
LAW_NAMES = {
    "blds_2015": "Bộ luật Dân sự 2015",
    "luat_nha_o_2023": "Luật Nhà ở 2023",
    "luat_kdbds_2023": "Luật Kinh doanh bất động sản 2023",
    "luat_cu_tru_68_2020": "Luật Cư trú 2020",
    "luat_quan_ly_thue_108_2025": "Luật Quản lý thuế 2025",
    "nd125_2020": "Nghị định 125/2020/NĐ-CP",
    "nd141_2026": "Nghị định 141/2026/NĐ-CP",
    "nd181_2025": "Nghị định 181/2025/NĐ-CP",
    "nd254_2026": "Nghị định 254/2026/NĐ-CP",
    "nd310_2025": "Nghị định 310/2025/NĐ-CP",
    "nd68_2026": "Nghị định 68/2026/NĐ-CP",
    "nd96_2024": "Nghị định 96/2024/NĐ-CP",
    "tt18_2026_btc": "Thông tư 18/2026/TT-BTC",
    "tt20_2026_btc": "Thông tư 20/2026/TT-BTC",
}


def law_name(law: str) -> str:
    return LAW_NAMES.get(law, law)


def ref_name(ref: str) -> str:
    """The KB's khoản/điểm ref as a reader writes it: "2" -> "khoản 2", "2.a" -> "khoản 2, điểm a"."""
    m = re.fullmatch(r"(\d+)(?:\.(\w+))?", ref)
    if m:
        return f"khoản {m.group(1)}" + (f", điểm {m.group(2)}" if m.group(2) else "")
    return f"điểm {ref}" if re.fullmatch(r"[a-zđ]", ref) else ref


@dataclass
class LegalBasis:
    law: str                   # KB law id, e.g. "luat_nha_o_2023"
    dieu: int | None
    ref: str                   # khoản / điểm within the Điều ("" = whole article)
    text: str                  # from the KB, never from the model
    why: str                   # "" now: legal_pick returns ids only
    source: str                # taxonomy | retrieval: how the passage became a candidate
    chunk_id: int

    @property
    def label(self) -> str:
        """"Bộ luật Dân sự 2015, Điều 468, khoản 1": how a citation is shown."""
        return f"{law_name(self.law)}, Điều {self.dieu}" + (f", {ref_name(self.ref)}" if self.ref else "")


@dataclass
class Candidate:
    id: str
    hit: Hit
    source: str


@functools.lru_cache(maxsize=None)
def _embedder(tag: str = DENSE_TAG):
    """The dense query encoder, loaded once per process (5-6 s); the per-run retriever objects stay cheap."""
    from application.modules.legal_retrieval.dense import CACHE, Embedder
    meta = json.loads((CACHE / f"vec_{tag}.json").read_text(encoding="utf-8"))
    return Embedder(meta["model"], meta["dim"], bf16=meta.get("bf16", False))


def warm() -> None:
    """Load the embedder and open the vector store ahead of the first analysis (the API calls this at startup)."""
    t = time.monotonic()
    try:
        retriever, warnings = default_retriever()
        log.info("retriever warmed in %.1fs%s", time.monotonic() - t, f" ({warnings[0]})" if warnings else "")
    except Exception as e:      # warming is an optimisation; the first run will report the real problem
        log.warning("retriever warm-up failed: %s", e)


def default_retriever(db_path=DEFAULT_DB) -> tuple[Retriever, list[str]]:
    """Hybrid BM25 + dense (embedded Qdrant); BM25 alone, with a warning, if the dense side cannot load."""
    lex = LexicalRetriever(db_path)
    try:
        t = time.monotonic()
        from application.modules.legal_retrieval.dense import HybridRetriever
        from application.modules.legal_retrieval.qdrant_store import QdrantRetriever
        log.info("retriever: imports %.1fs", time.monotonic() - t)
        t = time.monotonic()
        dense = QdrantRetriever(DENSE_TAG, db_path, embedder=_embedder())
        log.info("retriever: dense side (Qdrant + %s embedder) %.1fs", DENSE_TAG, time.monotonic() - t)
        return HybridRetriever(lex, dense), []
    except Exception as e:     # missing torch/qdrant, no index: still usable, just weaker
        log.warning("dense retrieval unavailable (%s); using BM25 only", e)
        return lex, [f"dense retrieval unavailable ({e}); legal basis uses BM25 only"]


def query_for(f: Finding, risk: taxonomy.Risk) -> str:
    return f"{f.issue} {f.quote}" if f.kind == "present" and f.quote else f"{f.issue} {risk.name}"


def _article_hits(con: sqlite3.Connection, law: str, dieu: int) -> list[Hit]:
    rows = con.execute("SELECT c.id, c.article_id, a.law, a.dieu_no, c.ref, 0.0, c.text FROM chunks c "
                       "JOIN articles a ON a.id = c.article_id WHERE a.law = ? AND a.dieu_no = ? ORDER BY c.id",
                       (law, dieu)).fetchall()
    return [Hit(*r) for r in rows]


def candidates(f: Finding, risk: taxonomy.Risk, retriever: Retriever, con: sqlite3.Connection,
               k: int = RETRIEVED) -> tuple[list[Candidate], list[str]]:
    q = query_for(f, risk)
    found: list[tuple[Hit, str]] = []
    warnings = []
    for c in risk.citations:
        if c["law"] is None:
            warnings.append(f"{risk.code}: cited law not in the KB, skipped: {c['text']}")
            continue
        if not c["dieu"]:
            found += [(h, "taxonomy") for h in retriever.search(q, PER_LAW, law=c["law"])]
            continue
        for d in c["dieu"]:
            art = _article_hits(con, c["law"], d)
            if not art:
                warnings.append(f"{risk.code}: {c['law']} Điều {d} is not in the KB, skipped")
                continue
            # an article can run to a dozen khoản: keep the ones retrieval ranks highest for this finding
            rank = {h.chunk_id: i for i, h in enumerate(retriever.search(q, 50, law=c["law"]))}
            art.sort(key=lambda h: rank.get(h.chunk_id, len(rank) + h.chunk_id))
            found += [(h, "taxonomy") for h in art[:PER_ARTICLE]]
    found += [(h, "retrieval") for h in retriever.search(q, k + 4) if h.law not in NOT_STATUTE][:k]
    out, seen = [], set()
    for h, src in found:
        if h.chunk_id not in seen:
            seen.add(h.chunk_id)
            out.append(Candidate(f"C{len(out) + 1}", h, src))
    return out, warnings


def _label(h: Hit) -> str:
    return f"{h.law}, Điều {h.dieu_no}" + (f", {h.ref}" if h.ref else "")


def parse_ids(text: str) -> list | None:
    """The picked ids from {"basis": [...]} or, as some models answer, a bare ["C1", ...] list; None if neither."""
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, text, re.S)
        if not m:
            continue
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        items = d.get("basis") if isinstance(d, dict) else d
        if isinstance(items, list):
            return items
    return None


def pick(f: Finding, risk: taxonomy.Risk, cands: list[Candidate], *, task: str = "legal_pick") -> dict:
    """-> {"basis": [LegalBasis], "warnings": [str], "attempt": {"raw", "finish", "usage", "model"} | None}"""
    if not cands:
        return {"basis": [], "warnings": [f"{f.code}: no candidate passages"], "attempt": None}
    prompt = PROMPT.format(
        max_picks=MAX_PICKS, code=f.code, name=risk.name, issue=f.issue,
        quote_line=f"Trích hợp đồng: «{f.quote}»\n" if f.quote else "Loại: nội dung hợp đồng còn thiếu\n",
        candidates="\n\n".join(f"[{c.id}] {_label(c.hit)}\n{c.hit.text[:MAX_CHARS]}" for c in cands))
    r = llm.chat(task, [{"role": "user", "content": prompt}])
    attempt = {"raw": r.text, "finish": r.finish_reason, "usage": r.usage, "model": r.model}
    items = parse_ids(r.text)
    if not isinstance(items, list):
        return {"basis": [], "warnings": [f"{f.code}: unparseable legal_pick reply; finish={r.finish_reason}"],
                "attempt": attempt}
    by_id = {c.id: c for c in cands}
    basis, warnings, used = [], [], set()
    for i in items[:MAX_PICKS]:
        # ids only (the explanation step says why); an older {"id", "why"} reply shape still reads
        cid = str(i.get("id", "") if isinstance(i, dict) else i).strip()
        c = by_id.get(cid)
        if c is None:
            warnings.append(f"{f.code}: picked {cid or i!r}, which is not a candidate; dropped")
            continue
        if cid in used:
            continue
        used.add(cid)
        why = str(i.get("why") or "").strip() if isinstance(i, dict) else ""
        basis.append(LegalBasis(c.hit.law, c.hit.dieu_no, c.hit.ref, c.hit.text, why, c.source, c.hit.chunk_id))
    return {"basis": basis, "warnings": warnings, "attempt": attempt}


def attach(findings: list[Finding], *, retriever: Retriever | None = None, tax: taxonomy.Taxonomy | None = None,
           db_path=DEFAULT_DB) -> list[dict]:
    """{"items": [{"code", "basis", "candidates", "warnings", "attempt"}] one per finding in the same order,
    "warnings": about the run (e.g. retrieval fell back to BM25)}. Findings come from M3, so every code is in the
    taxonomy."""
    tax = tax or taxonomy.load()
    run_warnings = []
    if retriever is None:
        retriever, run_warnings = default_retriever(db_path)
    con = sqlite3.connect(db_path)
    try:
        out = []
        t = time.monotonic()
        log.info("legal basis start: %d findings, retriever %s", len(findings), type(retriever).__name__)
        for f in findings:
            risk = tax.by_code[f.code]
            cands, warnings = candidates(f, risk, retriever, con)
            try:
                res = pick(f, risk, cands)
            except llm.LLMError as e:     # one failed call costs this finding its basis, not the run
                res = {"basis": [], "warnings": [f"{f.code}: legal_pick failed ({e})"], "attempt": None}
            log.debug("%s: %d candidates -> %s", f.code, len(cands),
                      ", ".join(f"{b.law} Đ{b.dieu} {b.ref}".strip() for b in res["basis"]) or "none")
            for w in warnings + res["warnings"]:
                log.warning(w)
            out.append({"code": f.code, "basis": res["basis"], "candidates": [_label(c.hit) for c in cands],
                        "warnings": warnings + res["warnings"],
                        "attempt": res["attempt"]})
        log.info("legal basis done: %d findings, %d with no basis, %.0fs", len(out),
                 sum(not i["basis"] for i in out), time.monotonic() - t)
        return {"items": out, "warnings": run_warnings}
    finally:
        con.close()
