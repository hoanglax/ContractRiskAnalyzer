"""Split a statute article into khoản / điểm retrieval units.

The retrieval unit is one complete quy phạm: a khoản (`1.`, `2.`), or an điểm (`a)`, `b)`) when the
khoản is longer than MAXCHARS. Each chunk's text is the article heading plus the unit, so a vector or
BM25 hit always carries its own context. The citation unit stays the whole Điều (see kb.py).
"""
import re

MAXCHARS = 550          # ~256 embedder tokens; a longer khoản is split by điểm
KHOAN_RE = re.compile(r"^[ \t]*(\d{1,2})[.)]\s+(?=\S)", re.M)
DIEM_RE = re.compile(r"^[ \t]*([a-zđ])[.)/]\s+(?=\S)", re.M)


def _by_diem(heading: str, text: str, pts: list[int], prefix: str) -> list[tuple[str, str]]:
    """Chunks for each điểm in `text`; the lead-in before the first điểm rides with the first one."""
    lead = text[:pts[0]].strip()
    out = []
    for j, start in enumerate(pts):
        end = pts[j + 1] if j + 1 < len(pts) else len(text)
        piece = text[start:end].strip()
        ref = prefix + DIEM_RE.match(piece).group(1)
        out.append((ref, f"{heading}\n{lead}\n{piece}" if j == 0 else f"{heading}\n{piece}"))
    return out


def khoan_split(heading: str, body: str, maxchars: int = MAXCHARS) -> list[tuple[str, str]]:
    """-> [(ref, text)]. ref is "" for an article with no khoản (one block), "2" for a khoản,
    "2.a" for an điểm of khoản 2, "a" for an điểm directly under the Điều."""
    body = body.strip()
    cuts = [m.start() for m in KHOAN_RE.finditer(body)]
    if not cuts:
        pts = [m.start() for m in DIEM_RE.finditer(body)]
        if len(pts) >= 2:
            return _by_diem(heading, body, pts, "")
        return [("", f"{heading}\n{body}".strip())]
    out = []
    for i, off in enumerate(cuts):
        seg = body[off:cuts[i + 1] if i + 1 < len(cuts) else len(body)].strip()
        ref = KHOAN_RE.match(seg).group(1)
        pts = [m.start() for m in DIEM_RE.finditer(seg)]
        if len(seg) <= maxchars or not pts:
            out.append((ref, f"{heading}\n{seg}"))
        else:
            out.extend(_by_diem(heading, seg, pts, f"{ref}."))
    return out
