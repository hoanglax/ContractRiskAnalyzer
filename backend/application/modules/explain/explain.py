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

from . import packet_context

log = logging.getLogger(__name__)
MAX_LAW_CHARS = 800
PARTY_VI = {"lessor": "bên cho thuê", "lessee": "bên thuê", "both": "cả hai bên"}
_LREF = re.compile(r"\[L(\d+)\]")
_PACKET_LREF = re.compile(r"\[\s*[Ll](?:\s*[+-]?\s*\d+|[A-Za-z0-9_-]*)\s*\]")
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


def _clusters(findings: list[Finding], bases: list[dict]) -> list[list[tuple[Finding, dict]]]:
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
    return clusters


def group(doc: Document, findings: list[Finding], bases: list[dict], tax: taxonomy.Taxonomy) -> list[Item]:
    """Items in contract order (missing last). `bases` is M4's items, aligned with `findings`."""
    return _group_items(doc, _clusters(findings, bases), tax)


def _group_items(doc, clusters, tax):
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


def check(reply: str, it: Item, *, packet_citations: bool = False) -> tuple[Explanation | None, str | None]:
    """The explanation with [Lk] resolved, or None and why it was dropped."""
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) and d[k].strip() for k in ("summary", "recommendation")):
        return None, "unparseable explain reply"
    text = d["summary"] + " " + d["recommendation"]
    if packet_citations:
        allowed_refs = {f"[L{i}]" for i in range(1, len(it.basis) + 1)}
        for ref in _PACKET_LREF.findall(text):
            if ref not in allowed_refs:
                safe_ref = ref if len(ref) <= 16 and ref.isascii() else "a malformed packet citation"
                return None, f"cites {safe_ref}, which is not in its legal basis"
        if re.search(_SELF_CITED.pattern, text, re.IGNORECASE):
            return None, "writes out a legal citation instead of using a packet citation ID"
    else:
        bad = sorted({int(n) for n in _LREF.findall(text) if not 1 <= int(n) <= len(it.basis)})
        if bad:
            return None, f"cites [L{bad[0]}], which is not in its legal basis"
    allowed = {b.dieu for b in it.basis}
    own = sorted({int(n) for n, _ in _SELF_CITED.findall(text) if int(n) not in allowed})
    if own:
        return None, f"writes out Điều {own[0]} of a law, which is not in its legal basis"
    cited = sorted({int(n) for n in _LREF.findall(text)})

    def resolve(s: str) -> str:
        s = _LREF.sub(lambda m: f"({it.basis[int(m.group(1)) - 1].label})", s)
        return re.sub(r"\)[\s,]*\(", "; ", s).strip()      # "[L1][L2]" -> one parenthesis

    return Explanation(resolve(d["summary"]), resolve(d["recommendation"]), [it.basis[n - 1].label for n in cited]), None


def explain(doc: Document, findings: list[Finding], bases: list[dict], *, tax: taxonomy.Taxonomy | None = None,
            task: str = "explain", context_run_id: str | None = None) -> dict:
    """{"items": [Item], "warnings": [str], "attempts": [{"codes", "raw", "finish", "usage", "model", "seconds"}]}"""
    tax = tax or taxonomy.load()
    if context_run_id is not None and len(findings) != len(bases):
        items = group(doc, findings, [{"basis": []} for _ in findings], tax)
        for it in items:
            it.warnings.append("no explanation: legal attachments do not align with findings")
        return {"items": items, "warnings": [], "attempts": []}
    clusters = _clusters(findings, bases)
    items = _group_items(doc, clusters, tax)
    t = time.monotonic()
    log.info("explain start: %d findings -> %d items", len(findings), len(items))
    attempts, warnings = [], []

    context = None
    messages_overridden = False
    if context_run_id is not None:
        try:
            context = packet_context.PacketContext.configure(context_run_id, task, tax)
        except packet_context.MessageOverrideError:
            messages_overridden = True
        except (ValueError, TypeError, llm.LLMError):
            warnings.append("context packet disabled for this run: check the explanation profile and context budget")

    def prepared():
        for it, cluster in zip(items, clusters):
            if messages_overridden:
                it.warnings.append("no explanation: model profile overrides explanation messages")
                continue
            if context_run_id is not None and any(
                "code" in basis and basis["code"] != finding.code for finding, basis in cluster
            ):
                it.basis = []
                it.warnings.append("no explanation: legal attachments do not align with findings")
                continue
            messages = [{"role": "user", "content": prompt_for(it, tax)}]
            if context is None:
                yield it, it, messages, False, None
                continue
            packet = None
            try:
                packet = context.build(doc, cluster)
                enhanced = context.enhanced(packet, it)
            except Exception as exc:
                it.warnings.append(f"context packet unavailable ({type(exc).__name__}); using legacy explanation if it fits")
                enhanced = None
            if packet is not None:
                it.warnings.extend(f"context packet: {code}" for code in dict.fromkeys(
                    diagnostic.code for diagnostic in packet.diagnostics
                ))
            if enhanced is not None:
                payload, scoped = enhanced
                yield it, scoped, payload, True, packet_context.trace_for(packet, scoped, enhanced=True)
                continue
            if packet is not None and any(
                d.code in {"invalid_legal_attachment", "conflicting_legal_attachment"}
                for d in packet.diagnostics
            ):
                it.warnings.append("no explanation: invalid or conflicting legal attachments")
                continue
            if packet is not None and packet.data and packet.data.guidance:
                it.warnings.append("context packet guidance omitted")
            if packet_context.message_size(messages) > context.budget.allowance:
                it.warnings.append("no explanation: context budget exceeded")
                continue
            trace = packet_context.trace_for(packet, it, enhanced=False) if packet else None
            yield it, it, messages, False, trace

    def one(job):
        try:
            if context is not None:
                return llm.chat(task, job[2], cfg=context.llm_config)
            return llm.chat(task, job[2])
        except llm.LLMError as e:
            return e

    for (it, scoped, _, enhanced, trace), r in llm.map_calls(task, one, prepared(), with_inputs=True):
        if isinstance(r, llm.LLMError):
            it.warnings.append(f"no explanation: {r}")
            log.warning("%s: no explanation (%s)", "+".join(it.codes), r)
            continue
        attempts.append({"codes": it.codes, "raw": r.text, "finish": r.finish_reason, "usage": r.usage, "model": r.model, "seconds": r.seconds})
        if trace is not None:
            attempts[-1]["context_packet"] = trace
        it.explanation, why = check(r.text, scoped, packet_citations=enhanced)
        if why:
            it.warnings.append(f"explanation dropped: {why}")
            log.warning("%s: explanation dropped: %s", "+".join(it.codes), why)
    log.info("explain done: %d items, %d without explanation, %.0fs", len(items),
             sum(it.explanation is None for it in items), time.monotonic() - t)
    return {"items": items, "warnings": warnings, "attempts": attempts}
