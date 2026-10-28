"""Detector v0: the whole contract in one call, against a closed list of risks (the taxonomy, as LookFor).

Contracts here are short (median ~2.7k tokens), so the model sees every clause at once and can report terms that
are missing or that contradict each other. Every finding must name one code from the list; ground() rejects the
rest. Rejected items are sent back once more with the reason (at most RETRIES times) so a mis-copied quote or a
mistyped code can be fixed without losing the findings that passed; whatever is still rejected becomes a warning.

detect() puts the whole list in one prompt; detect_by_group() makes one call per taxonomy group, each with a
shorter list. Which works better is measured on the eval set (proposal D1).
"""
from __future__ import annotations

import json
import re

from application.adapters import llm
from application.modules.detection.finding import Finding, LookFor, ground
from application.modules.ingestion.ingest import Document

RETRIES = 2

PROMPT = """Bạn là luật sư rà soát hợp đồng thuê nhà ở theo pháp luật Việt Nam. Hãy đọc hợp đồng và tìm những rủi ro trong DANH SÁCH RỦI RO bên dưới: điều khoản có rủi ro đó, hoặc nội dung cần thiết mà hợp đồng thiếu.

Quy tắc:
- Chỉ báo rủi ro có trong danh sách. Mỗi phát hiện ghi đúng MỘT mã ("code") lấy từ danh sách. Rủi ro không khớp mã nào thì không báo.
- Với điều khoản có vấn đề ("kind": "present"), "quote" phải chép NGUYÊN VĂN, liên tục, từ hợp đồng: không sửa chữ, không tóm tắt, không thêm dấu "...". Chỉ chép phần gây rủi ro (thường một câu), không chép cả điều.
- Với nội dung hợp đồng thiếu ("kind": "missing"), để "quote" là null.
- Các chỗ trống "......" trong mẫu hợp đồng là để điền thông tin, bản thân chúng không phải rủi ro.
- Không báo các điều khoản công bằng, đúng luật.
- Mã bắt đầu bằng A là rủi ro của bên cho thuê, B là rủi ro của bên thuê. Một điều khoản gây rủi ro cho cả hai bên thì báo hai lần, mỗi lần một mã.
- "issue": một hai câu tiếng Việt nêu vấn đề và lý do, gắn với nội dung cụ thể của hợp đồng này.

Chỉ trả lời bằng JSON:
{{"findings": [{{"code": "...", "kind": "present" | "missing", "quote": "..." | null, "issue": "..."}}]}}

DANH SÁCH RỦI RO:
{lens}

HỢP ĐỒNG:
{contract}"""

FIX = """Một số phát hiện của bạn bị loại khi kiểm tra:
{items}

Hãy sửa từng mục: chép lại "quote" NGUYÊN VĂN từ hợp đồng, hoặc dùng đúng mã trong danh sách. Mục nào không sửa được thì bỏ.
Các phát hiện khác đã được giữ, không cần gửi lại. Chỉ trả lời bằng JSON cùng định dạng: {{"findings": [...]}}"""

FIX_JSON = 'Câu trả lời trên không đọc được ({why}). Hãy trả lời lại, chỉ bằng JSON: {{"findings": [...]}}'

WHY_VI = {"quote not found verbatim in the contract": "trích dẫn không khớp nguyên văn hợp đồng",
          "no quote": "thiếu trích dẫn cho phát hiện present", "no code": "thiếu mã",
          "no issue given": "thiếu mô tả vấn đề"}


def render_lens(lens: list[LookFor]) -> str:
    return "\n".join(f"- [{l.id}] {l.title}" + (f": {l.signs}" if l.signs else "") for l in lens)


def parse(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    items = json.loads(m.group(0)).get("findings", [])
    if not isinstance(items, list):
        raise ValueError("'findings' is not a list")
    return [i for i in items if isinstance(i, dict)]


def _why_vi(why: str) -> str:
    if why.startswith("unknown code"):
        return f"mã {why.removeprefix('unknown code ')} không có trong danh sách"
    if why.startswith("unknown kind"):
        return f"kind {why.removeprefix('unknown kind ')} không hợp lệ (chỉ present hoặc missing)"
    return WHY_VI.get(why, why)


def fix_prompt(rejected: list[tuple[Finding, str]]) -> str:
    items = "\n".join(json.dumps({"code": f.code, "kind": f.kind, "quote": f.quote, "issue": f.issue,
                                  "lỗi": _why_vi(why)}, ensure_ascii=False) for f, why in rejected)
    return FIX.format(items=items)


def detect(doc: Document, lens: list[LookFor], *, task: str = "detect", max_tokens: int = 8000,
           temperature: float | None = None, retries: int = RETRIES) -> dict:
    """-> {"kept": [Finding], "rejected": [(Finding, why)], "warnings": [str], "error": str|None,
           "attempts": [{"raw", "finish", "usage", "model", "kept", "rejected", "error"}]}
    "rejected" holds what was still rejected after the last retry. temperature None = the LLM profile's (0 by
    default, so repeated runs give the same answer)."""
    if not lens:
        raise ValueError("detect needs a non-empty list of risks to look for")
    prompt = PROMPT.format(contract=doc.text, lens=render_lens(lens))
    sampling = {"max_tokens": max_tokens, **({"temperature": temperature} if temperature is not None else {})}
    messages = [{"role": "user", "content": prompt}]
    out = {"kept": [], "rejected": [], "warnings": [], "error": None, "attempts": []}
    for attempt in range(retries + 1):
        r = llm.chat(task, list(messages), sampling=sampling)
        rec = {"raw": r.text, "finish": r.finish_reason, "usage": r.usage, "model": r.model,
               "kept": 0, "rejected": [], "error": None}
        out["attempts"].append(rec)
        messages.append({"role": "assistant", "content": r.text})
        try:
            items = parse(r.text)
        except (ValueError, json.JSONDecodeError) as e:
            rec["error"] = f"unparseable reply ({e}); finish={r.finish_reason}"
            # a broken retry keeps the earlier findings and their rejections; only a broken first reply is fatal
            if attempt == 0:
                out["error"] = rec["error"]
            messages.append({"role": "user", "content": FIX_JSON.format(why=e)})
            continue
        tag = f"whole_doc:{r.model}"
        findings = [Finding(kind=str(i.get("kind", "")), issue=str(i.get("issue") or ""), quote=i.get("quote"),
                            code=str(i["code"]).strip() if i.get("code") else None, detector=tag)
                    for i in items]
        kept, rejected = ground(findings, doc, lens)
        out["kept"] += kept
        out["rejected"] = rejected
        out["error"] = None
        rec["kept"], rec["rejected"] = len(kept), [{"code": f.code, "quote": f.quote, "why": w} for f, w in rejected]
        if not rejected:
            break
        messages.append({"role": "user", "content": fix_prompt(rejected)})
    if out["error"] is None:
        out["warnings"] += [f"dropped after {len(out['attempts'])} attempts: {f.code} {f.kind} "
                            f"«{(f.quote or '')[:80]}»: {why}" for f, why in out["rejected"]]
    return out


def detect_by_group(doc: Document, lens: list[LookFor], **kw) -> dict:
    """One detect() call per taxonomy group (LookFor.meta["group"]), results merged."""
    groups: dict[str, list[LookFor]] = {}
    for l in lens:
        groups.setdefault(l.meta.get("group", ""), []).append(l)
    out = {"kept": [], "rejected": [], "warnings": [], "error": None, "attempts": []}
    errors = []
    for g, ls in groups.items():
        r = detect(doc, ls, **kw)
        out["kept"] += r["kept"]
        out["rejected"] += r["rejected"]
        out["warnings"] += r["warnings"]
        out["attempts"] += [{**a, "group": g} for a in r["attempts"]]
        if r["error"]:
            errors.append(f"group {g}: {r['error']}")
    # one broken group must not throw away the others' findings
    if errors and len(errors) == len(groups):
        out["error"] = "; ".join(errors)
    else:
        out["warnings"] += [f"no findings from {e}" for e in errors]
    return out
