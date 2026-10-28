"""M6: one plain-Vietnamese explanation and recommendation per contract clause, built from M3 findings and M4 bases.

    from application.modules.explain.explain import explain
    out = explain(doc, findings, bases["items"])    # {"items": [Item], "warnings": [str]}

Grouping: detection reports one finding per taxonomy code, so one clause often comes back under several codes (an
A- and a B- row, or neighbouring rows). Present findings whose quotes overlap become one Item listing every code;
each missing finding is an Item of its own. Severity is the highest of the item's rows; parties are all of them.

The model writes the explanation (task "explain") and may cite law only as [L1], [L2] ... from the item's legal
basis list; the code turns those into "Bộ luật Dân sự 2015, Điều 468, khoản 1". An unknown [L] id, or an article it
wrote out itself that is not in the list, drops the explanation with a warning: the item is still shown with the
taxonomy's name, severity and consequences.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from application.adapters import llm
from application.modules.detection.finding import Finding
from application.modules.ingestion.ingest import Document
from application.modules.legal_basis.basis import LegalBasis
from application.modules.taxonomy import taxonomy

log = logging.getLogger(__name__)
MAX_LAW_CHARS = 800
PARTY_VI = {"lessor": "bên cho thuê", "lessee": "bên thuê", "both": "cả hai bên"}
_LREF = re.compile(r"\[L(\d+)\]")
# a law article written out by the model: "Điều 468 Bộ luật Dân sự", "Điều 172 khoản 1 của Luật Nhà ở" ...
_SELF_CITED = re.compile(r"Điều\s+(\d+)\b[^.\n\[]{0,40}?\b(Bộ luật|Luật|BLDS|Nghị định|NĐ|Thông tư|TT)\b")

PROMPT = """Bạn là luật sư tư vấn cho người dân về hợp đồng thuê nhà ở. Hãy giải thích rủi ro dưới đây bằng tiếng Việt dễ hiểu cho người không học luật.

{what}

RỦI RO (theo danh mục rủi ro):
{risks}

CĂN CỨ PHÁP LÝ (chỉ được dùng các đoạn này):
{laws}

Yêu cầu:
- "summary": 2-4 câu: điều khoản này có nghĩa là gì trong thực tế, và vì sao gây bất lợi cho {parties}.
- "recommendation": 1-3 câu: nên hỏi lại hoặc đề nghị sửa gì trước khi ký, cụ thể cho hợp đồng này.
- Khi nhắc tới quy định pháp luật, chỉ ghi mã đoạn trong ngoặc vuông, ví dụ [L1]. KHÔNG tự viết số điều, tên luật, hay quy định không có trong danh sách.{no_law}
- Không lặp lại nguyên văn danh mục rủi ro; tập trung vào hợp đồng này.

Chỉ trả lời bằng JSON: {{"summary": "...", "recommendation": "..."}}"""


@dataclass
class Explanation:
    summary: str               # [Lk] already replaced by the citation it stands for
    recommendation: str
    cited: list[str] = field(default_factory=list)    # labels of the bases it cited


@dataclass
class Item:
    """One card of the result: a clause (or a missing term) with every code reported for it."""
    kind: str                  # present | missing
    codes: list[str]
    severity: str              # the highest of the codes' rows
    parties: list[str]         # lessor / lessee, from the rows
    issues: dict[str, str]     # code -> the detector's issue for this contract
    quote: str | None = None   # contract text over the merged span (present only)
    clause: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    basis: list[LegalBasis] = field(default_factory=list)    # union over the codes, one per passage
    explanation: Explanation | None = None
    warnings: list[str] = field(default_factory=list)


def group(doc: Document, findings: list[Finding], bases: list[dict], tax: taxonomy.Taxonomy) -> list[Item]:
    """Items in contract order (missing last). `bases` is M4's items, aligned with `findings`."""
    pairs = list(zip(findings, bases))
    present = sorted((p for p in pairs if p[0].kind == "present"), key=lambda p: (p[0].char_start, -p[0].char_end))
    clusters: list[list[tuple[Finding, dict]]] = []
    end = -1
    for p in present:
        if clusters and p[0].char_start < end:
            clusters[-1].append(p)
            end = max(end, p[0].char_end)
        else:
            clusters.append([p])
            end = p[0].char_end
    clusters += [[p] for p in pairs if p[0].kind != "present"]
    order = taxonomy.SEVERITIES
    items = []
    for c in clusters:
        rows = [tax.by_code[f.code] for f, _ in c]
        basis = list({b.chunk_id: b for _, bs in c for b in bs["basis"]}.values())
        f0 = c[0][0]
        it = Item(kind=f0.kind, codes=list(dict.fromkeys(f.code for f, _ in c)),
                  severity=max((r.severity for r in rows), key=order.index),
                  parties=sorted({f.affects for f, _ in c if f.affects}),
                  issues={f.code: f.issue for f, _ in c}, basis=basis)
        if f0.kind == "present":
            it.char_start, it.char_end = min(f.char_start for f, _ in c), max(f.char_end for f, _ in c)
            it.quote, it.clause = doc.text[it.char_start:it.char_end], f0.clause
        items.append(it)
    return items


def prompt_for(it: Item, tax: taxonomy.Taxonomy) -> str:
    what = (f"ĐIỀU KHOẢN TRONG HỢP ĐỒNG ({it.clause or 'phần đầu hợp đồng'}):\n«{it.quote}»" if it.kind == "present"
            else "NỘI DUNG HỢP ĐỒNG CÒN THIẾU (không có điều khoản tương ứng).")
    risks = []
    for code in it.codes:
        r = tax.by_code[code]
        risks.append(f"- [{code}] {r.name} (mức độ {r.severity}; rủi ro của "
                     f"{'bên cho thuê' if r.party == 'A' else 'bên thuê'})\n  Nhận định cho hợp đồng này: {it.issues[code]}"
                     + (f"\n  Hậu quả thường gặp: {'; '.join(r.consequences)}" if r.consequences else ""))
    laws = "\n\n".join(f"[L{i}] {b.label}\n{b.text[:MAX_LAW_CHARS]}" for i, b in enumerate(it.basis, 1))
    return PROMPT.format(what=what, risks="\n".join(risks), laws=laws or "(không có)",
                         parties=" và ".join(PARTY_VI[p] for p in it.parties) or "các bên",
                         no_law="" if it.basis else " Danh sách trống: không nhắc tới điều luật nào.")


def check(reply: str, it: Item) -> tuple[Explanation | None, str | None]:
    """The explanation with [Lk] resolved, or None and why it was dropped."""
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) and d[k].strip() for k in ("summary", "recommendation")):
        return None, "unparseable explain reply"
    text = d["summary"] + " " + d["recommendation"]
    bad = sorted({int(n) for n in _LREF.findall(text) if not 1 <= int(n) <= len(it.basis)})
    if bad:
        return None, f"cites [L{bad[0]}], which is not in its legal basis"
    allowed = {b.dieu for b in it.basis}
    own = sorted({int(n) for n, _ in _SELF_CITED.findall(text) if int(n) not in allowed})
    if own:
        return None, f"writes out Điều {own[0]} of a law, which is not in its legal basis"
    cited = sorted({int(n) for n in _LREF.findall(text)})

    def resolve(s: str) -> str:
        return _LREF.sub(lambda m: f"({it.basis[int(m.group(1)) - 1].label})", s).strip()

    return Explanation(resolve(d["summary"]), resolve(d["recommendation"]), [it.basis[n - 1].label for n in cited]), None


def explain(doc: Document, findings: list[Finding], bases: list[dict], *, tax: taxonomy.Taxonomy | None = None,
            task: str = "explain") -> dict:
    """{"items": [Item], "warnings": [str], "attempts": [{"codes", "raw", "finish", "usage", "model"}]}"""
    tax = tax or taxonomy.load()
    items = group(doc, findings, bases, tax)
    t = time.monotonic()
    log.info("explain start: %d findings -> %d items", len(findings), len(items))
    attempts, warnings = [], []
    for it in items:
        try:
            r = llm.chat(task, [{"role": "user", "content": prompt_for(it, tax)}])
        except llm.LLMError as e:
            it.warnings.append(f"no explanation: {e}")
            log.warning("%s: no explanation (%s)", "+".join(it.codes), e)
            continue
        attempts.append({"codes": it.codes, "raw": r.text, "finish": r.finish_reason, "usage": r.usage, "model": r.model})
        it.explanation, why = check(r.text, it)
        if why:
            it.warnings.append(f"explanation dropped: {why}")
            log.warning("%s: explanation dropped: %s", "+".join(it.codes), why)
    log.info("explain done: %d items, %d without explanation, %.0fs", len(items),
             sum(it.explanation is None for it in items), time.monotonic() - t)
    return {"items": items, "warnings": warnings, "attempts": attempts}
