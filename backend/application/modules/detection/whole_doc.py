"""Detector v0: the whole contract in one call, with an optional LookFor list as a checklist.

Contracts here are short (median ~2.7k tokens), so the model sees every clause at once and can report terms that
are missing or that contradict each other. The LookFor list is optional and its ids are only echoed back, so the
same detector runs with the taxonomy, another list, or none. Output goes through ground() like any detector's.
"""
from __future__ import annotations

import json
import re

from application.adapters import llm
from application.modules.detection.finding import Finding, LookFor, ground
from application.modules.ingestion.ingest import Document

PROMPT = """Bạn là luật sư rà soát hợp đồng thuê nhà ở theo pháp luật Việt Nam. Hãy tìm mọi điều khoản gây rủi ro hoặc bất lợi cho bên cho thuê hoặc bên thuê: trái luật, mập mờ, một chiều, mâu thuẫn với điều khoản khác, và những nội dung cần thiết mà hợp đồng thiếu.

Quy tắc:
- Với điều khoản có vấn đề ("kind": "present"), "quote" phải chép NGUYÊN VĂN, liên tục, từ hợp đồng: không sửa chữ, không tóm tắt, không thêm dấu "...". Chỉ chép phần gây rủi ro (thường một câu), không chép cả điều.
- Với nội dung hợp đồng thiếu ("kind": "missing"), để "quote" là null.
- Các chỗ trống "......" trong mẫu hợp đồng là để điền thông tin, bản thân chúng không phải rủi ro.
- Không báo các điều khoản công bằng, đúng luật.
- "affects": bên chịu rủi ro, "lessor" (bên cho thuê), "lessee" (bên thuê) hoặc "both".
- "issue": một hai câu tiếng Việt nêu vấn đề và lý do.
{lens_rules}
Chỉ trả lời bằng JSON:
{{"findings": [{{"kind": "present" | "missing", "quote": "..." | null, "issue": "...", "affects": "lessor" | "lessee" | "both"{lens_field}}}]}}

HỢP ĐỒNG:
{contract}
{lens}"""

LENS_RULES = ("- Danh sách bên dưới gợi ý những rủi ro thường gặp; dùng để rà soát, nhưng vẫn báo cả rủi ro không có trong danh sách. "
              "Ghi vào \"lens\" mã các mục liên quan (có thể để trống).\n")


def render_lens(lens: list[LookFor]) -> str:
    lines = [f"- [{l.id}] {l.title}" + (f": {l.signs}" if l.signs else "") for l in lens]
    return "\nDANH SÁCH GỢI Ý:\n" + "\n".join(lines) + "\n"


def parse(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    items = json.loads(m.group(0)).get("findings", [])
    if not isinstance(items, list):
        raise ValueError("'findings' is not a list")
    return [i for i in items if isinstance(i, dict)]


def detect(doc: Document, lens: list[LookFor] | None = None, *, task: str = "detect",
           max_tokens: int = 8000, temperature: float | None = None) -> dict:
    """-> {"kept": [Finding], "rejected": [(Finding, why)], "raw": str, "finish": str, "usage": dict, "error": str|None}
    temperature None = the LLM profile's (0 by default, so repeated runs give the same answer)."""
    prompt = PROMPT.format(contract=doc.text, lens=render_lens(lens) if lens else "",
                           lens_rules=LENS_RULES if lens else "", lens_field=', "lens": ["..."]' if lens else "")
    sampling = {"max_tokens": max_tokens, **({"temperature": temperature} if temperature is not None else {})}
    r = llm.chat(task, [{"role": "user", "content": prompt}], sampling=sampling)
    out = {"kept": [], "rejected": [], "raw": r.text, "finish": r.finish_reason, "usage": r.usage, "error": None}
    try:
        items = parse(r.text)
    except (ValueError, json.JSONDecodeError) as e:
        out["error"] = f"unparseable reply ({e}); finish={r.finish_reason}"
        return out
    tag = f"whole_doc{'+lens' if lens else ''}:{r.model}"
    findings = [Finding(kind=str(i.get("kind", "")), issue=str(i.get("issue") or ""), quote=i.get("quote"),
                        affects=i.get("affects"), lens=[str(x) for x in i.get("lens") or []], detector=tag)
                for i in items]
    out["kept"], out["rejected"] = ground(findings, doc)
    return out
