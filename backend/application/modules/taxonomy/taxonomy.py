"""Risk taxonomy: data/Risk Taxonomy.xlsx -> data/taxonomy/taxonomy.json, and loading it.

The workbook is the source of truth (the data team edits it); the JSON is generated from it and committed, so a
change to the taxonomy shows up in review and the app needs no xlsx reader at runtime. build() normalises what the
sheets spell inconsistently (codes "A - AUT - 01" / "A-RES-01", severity typos) and resolves each cited statute to a
KB law id (file stem, as in application.modules.legal_retrieval.kb). Whatever it had to correct or could not resolve is listed in "issues", to
be fixed in the workbook. Stdlib only.

    python -m application.modules.taxonomy.taxonomy build [--xlsx PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DEFAULT_XLSX = REPO / "data" / "Risk Taxonomy.xlsx"
DEFAULT_JSON = REPO / "data" / "taxonomy" / "taxonomy.json"

SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
PARTIES = {"A": "Bên cho thuê", "B": "Bên thuê"}
COLUMNS = {"Mã": "code", "Tên": "name", "Mức độ": "severity", "Dấu hiệu nhận biết": "signs",
           "Căn cứ pháp lý": "legal_basis", "Rủi ro thực tế": "consequences", "Nhãn": "labels"}

# statute names as the workbook writes them (lowercased) -> KB law id
LAWS = {
    "blds 2015": "blds_2015",
    "luật nhà ở 2023": "luat_nha_o_2023",
    "luật kdbđs 2023": "luat_kdbds_2023",
    "luật kinh doanh bất động sản 2023": "luat_kdbds_2023",
    "luật cư trú 2020": "luat_cu_tru_68_2020",
    "luật quản lý thuế 108/2025/qh15": "luat_quan_ly_thue_108_2025",
    "luật quản lý thuế 2025": "luat_quan_ly_thue_108_2025",
    "nghị định 68/2026/nđ-cp": "nd68_2026",
    "nghị định 254/2026/nđ-cp": "nd254_2026",
    "nghị định 125/2020/nđ-cp": "nd125_2020",
    "nghị định 181/2025/nđ-cp": "nd181_2025",
    "thông tư 18/2026/tt-btc": "tt18_2026_btc",
    "thông tư 20/2026/tt-btc": "tt20_2026_btc",
}
LAW_TYPOS = {    # resolved, but reported so the workbook gets fixed
    "bldc 2015": "blds_2015",
    "bdls 2015": "blds_2015",
    "bộ luật kinh doanh bất động sản 2023": "luat_kdbds_2023",
}

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _norm(s: str) -> str:
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFC", s)).strip()


def read_xlsx(path: Path) -> dict[str, list[list[str]]]:
    """Every sheet as rows of cell strings (column A first, empty cells ""), in workbook order."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        strings = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS}si"):
                strings.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for sh in ET.fromstring(z.read("xl/workbook.xml")).find(f"{_NS}sheets"):
            target = rels[sh.get(_REL)].lstrip("/").removeprefix("xl/")
            rows = []
            for row in ET.fromstring(z.read("xl/" + target)).iter(f"{_NS}row"):
                cells = {}
                for c in row.findall(f"{_NS}c"):
                    col = re.match(r"[A-Z]+", c.get("r")).group(0)
                    v, inline = c.find(f"{_NS}v"), c.find(f"{_NS}is")
                    if c.get("t") == "s" and v is not None:
                        val = strings[int(v.text)]
                    elif inline is not None:
                        val = "".join(t.text or "" for t in inline.iter(f"{_NS}t"))
                    else:
                        val = v.text if v is not None else ""
                    cells[_col_index(col)] = val or ""
                width = max(cells, default=-1) + 1
                rows.append([cells.get(i, "") for i in range(width)])
            sheets[sh.get("name")] = rows
    return sheets


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n - 1


def parse_citations(text: str, code: str, issues: list[str]) -> list[dict]:
    """'Điều 117, 141 BLDS 2015\\nĐiều 11 Luật Nhà ở 2023' -> [{law, dieu, text}]; law is None if unknown."""
    out = []
    for line in _norm(text).split("\n"):
        for part in re.split(r",\s*(?=Điều)", line.strip()):
            part = part.strip().rstrip(",;.").strip()
            if not part:
                continue
            m = re.match(r"Điều\s*([\d,/\s]+?)\s+(\D.*)$", part)
            nums, name = ([int(n) for n in re.findall(r"\d+", m.group(1))], m.group(2)) if m else ([], part)
            key = _norm(name).lower()
            law = LAWS.get(key) or LAW_TYPOS.get(key)
            if key in LAW_TYPOS:
                issues.append(f"{code}: statute written '{name}', read as {law}")
            elif law is None:
                issues.append(f"{code}: cites '{name}', which is not in the KB")
            out.append({"law": law, "dieu": nums, "text": part})
    return out


def _severity(raw: str, code: str, issues: list[str]) -> str:
    s = _norm(raw).upper()
    if s in SEVERITIES:
        return s
    close = difflib.get_close_matches(s, SEVERITIES, n=1, cutoff=0.6)
    if not close:
        raise ValueError(f"{code}: unknown severity {raw!r}")
    issues.append(f"{code}: severity '{raw}' read as {close[0]}")
    return close[0]


def _scale(rows: list[list[str]]) -> dict[str, str]:
    """The 'Quy ước' sheet: '1. LOW:' in one row, its description in the next non-empty one."""
    cells = [_norm(c) for r in rows for c in r if _norm(c)]
    scale = {}
    for i, c in enumerate(cells):
        m = re.fullmatch(r"\d+\.\s*([A-Z]+):?", c)
        if m and m.group(1) in SEVERITIES and i + 1 < len(cells):
            scale[m.group(1)] = cells[i + 1]
    return scale


def build(sheets: dict[str, list[list[str]]]) -> dict:
    issues, groups, risks = [], [], []
    scale = {}
    for name, rows in sheets.items():
        if name.strip().lower() == "quy ước":
            scale = _scale(rows)
            continue
        hdr = next((i for i, r in enumerate(rows) if any(_norm(c) == "Mã" for c in r)), None)
        if hdr is None:
            continue
        cols = {COLUMNS[_norm(c)]: j for j, c in enumerate(rows[hdr]) if _norm(c) in COLUMNS}
        title = next(_norm(c) for r in rows[:hdr] for c in r if _norm(c))
        m = re.match(r"(\d+)\s*[,.]\s*(?:NHÓM\s+)?(.*?)\s*\((.*)\)\s*$", title)
        if not m:
            raise ValueError(f"sheet {name!r}: cannot read the group title {title!r}")
        group = {"n": int(m.group(1)), "name": m.group(2), "name_en": m.group(3), "code": None}

        def cell(r, k):
            j = cols.get(k)
            return _norm(r[j]) if j is not None and j < len(r) else ""

        for r in rows[hdr + 1:]:
            raw = cell(r, "code")
            if not raw:
                continue
            code = re.sub(r"\s+", "", raw).upper()
            if not re.fullmatch(r"[AB]-[A-Z]{3}-\d{2}", code):
                raise ValueError(f"sheet {name!r}: bad risk code {raw!r}")
            gcode = code[2:5]
            if group["code"] not in (None, gcode):
                issues.append(f"{code}: group code differs from {group['code']} in the same sheet")
            group["code"] = group["code"] or gcode
            risks.append({
                "code": code, "party": code[0], "group": gcode, "name": cell(r, "name"),
                "severity": _severity(cell(r, "severity"), code, issues),
                "signs": cell(r, "signs"),
                "legal_basis": cell(r, "legal_basis"),
                "citations": parse_citations(cell(r, "legal_basis"), code, issues),
                "consequences": [l.strip() for l in cell(r, "consequences").split("\n") if l.strip()],
                "labels": [l.strip() for l in re.split(r"[,\n]", cell(r, "labels")) if l.strip()],
            })
        groups.append(group)
    seen = set()
    for r in risks:
        if r["code"] in seen:
            raise ValueError(f"duplicate risk code {r['code']}")
        seen.add(r["code"])
    if set(scale) != set(SEVERITIES):
        issues.append(f"severity scale has {sorted(scale)}, expected {SEVERITIES}")
    return {"severity_scale": scale, "parties": PARTIES, "groups": groups, "risks": risks, "issues": issues}


@dataclass
class Risk:
    code: str                  # "B-DEP-04"
    party: str                 # A (lessor) | B (lessee): whose risk it is
    group: str                 # "DEP"
    name: str
    severity: str              # LOW | MEDIUM | HIGH | CRITICAL
    signs: str                 # how to recognise it in a contract
    legal_basis: str           # as written in the workbook
    citations: list[dict] = field(default_factory=list)   # {law: KB id | None, dieu: [int], text}
    consequences: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class Taxonomy:
    severity_scale: dict[str, str]
    parties: dict[str, str]
    groups: list[dict]         # {n, code, name, name_en}
    risks: list[Risk]
    issues: list[str]

    def __post_init__(self):
        self.by_code = {r.code: r for r in self.risks}

    def in_group(self, group: str, party: str | None = None) -> list[Risk]:
        return [r for r in self.risks if r.group == group and (party is None or r.party == party)]


def load(path: Path = DEFAULT_JSON) -> Taxonomy:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Taxonomy(d["severity_scale"], d["parties"], d["groups"], [Risk(**r) for r in d["risks"]], d["issues"])


def dumps(tax: dict) -> str:
    return json.dumps(tax, ensure_ascii=False, indent=1) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--out", type=Path, default=DEFAULT_JSON)
    a = ap.parse_args()
    tax = build(read_xlsx(a.xlsx))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(dumps(tax), encoding="utf-8")
    print(f"{len(tax['risks'])} risks in {len(tax['groups'])} groups -> {a.out}")
    for g in tax["groups"]:
        print(f"  {g['n']} {g['code']} {len([r for r in tax['risks'] if r['group'] == g['code']]):3}  {g['name']}")
    if tax["issues"]:
        print(f"{len(tax['issues'])} issues to fix in the workbook:")
        for i in tax["issues"]:
            print("  " + i)


if __name__ == "__main__":
    main()
