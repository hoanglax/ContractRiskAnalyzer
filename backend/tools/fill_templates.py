"""Step 0 of the synthetic eval set: fill contract templates into complete, fair, fictional contracts.

    cd backend && .venv/bin/python tools/fill_templates.py [--variants 5] [--only 24,60] [--workers 4] [--limit N]

Each template in data/test/templates (minus PREFILLED and DUPLICATE_OF below) gets N variants. A variant is a seeded random profile (parties, ID numbers,
addresses, property, rent, deposit, dates; all fictional) handed to a local LLM, which rewrites the template with
every blank filled. Nothing here is a planted risk: the target is a clean, complete base for step 1 (planting).

The template's own wording is the contract, so it must survive: the filled text is diffed against the template word
by word, and every template word the model deleted or changed is a violation (blanks such as "....", "___" and
"(ĐIỀN HỌ TÊN)" placeholders may go). One retry quotes the violations back; a variant still violating is
flagged. Inserted text (the fills, and fair content for clauses the template leaves "do các bên
thỏa thuận") is recorded as spans, so later steps know what the model wrote.

The checks only sort, they do not judge: a variant that passes all of them goes to ok/, anything else (lost template
words, leftover blanks, missing party names, cut off output) goes to flagged/ for human review, with the reasons in
"flags". The word diff has known false positives (a fill glued to a word, "....đồng" -> "5.000.000đồng"), which is
fine: a person looks at every flagged variant and moves it to ok/ or deletes it.

Output, per variant, in data/test/synth/filled/{ok,flagged}/:
  <template>_v<k>.txt         the filled contract (clean() text, stable under ingest)
  <template>_v<k>.json        template, seed, profile, status, flags, violations, leftover blanks, inserted spans, usage
Existing outputs (in either folder) are skipped, so an interrupted run resumes.

Model: the local llama-server (default http://127.0.0.1:9876/v1, --base-url to change); contract text is fictional,
but the step is meant to be free, so no cloud profile is used.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["STRUCTURE_LLM"] = "off"

from application.adapters import llm  # noqa: E402
from application.modules.ingestion.ingest import ingest  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "test"
TEMPLATES = DATA / "templates"
OUT = DATA / "synth" / "filled"
log = logging.getLogger("fill")

# Templates not filled (audit 2026-11-02: a 27B read of every template, then checked by hand; duplicates by text
# similarity >= 0.97). A template that already carries values cannot be filled under the "template words survive"
# rule, and duplicates would only repeat one contract. The files stay: other tools use them.
PREFILLED = {   # a real contract with names, ID numbers, addresses, amounts
    "9", "17", "19", "20", "49", "78", "89", "90", "92", "97",
    # sample values (NGUYỄN VĂN A, "123xxx" IDs) plus concrete prices and dates
    "0", "6", "10", "26", "50", "70", "83", "88"}
DUPLICATE_OF = {"7": "24", "45": "35", "81": "35", "76": "43", "77": "43", "48": "46", "58": "46", "68": "46",
                "64": "47", "65": "47", "56": "54", "59": "54", "57": "55", "62": "61", "86": "84"}

# ---------------- fictional profile ----------------

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô",
      "Dương", "Lý", "Đinh", "Trịnh", "Mai", "Tô", "Lưu", "Cao", "Lâm", "Tạ"]
DEM_NAM = ["Văn", "Hữu", "Đức", "Minh", "Quang", "Thành", "Công", "Gia", "Xuân", "Ngọc", "Trọng", "Anh"]
DEM_NU = ["Thị", "Ngọc", "Thu", "Thanh", "Minh", "Phương", "Hồng", "Kim", "Mỹ", "Bảo", "Diệu", "Khánh"]
TEN_NAM = ["An", "Bình", "Cường", "Dũng", "Đạt", "Hải", "Hiếu", "Hoàng", "Hùng", "Khoa", "Long", "Nam", "Phong",
           "Quân", "Sơn", "Tài", "Thắng", "Toàn", "Trung", "Tuấn", "Việt", "Vinh"]
TEN_NU = ["Anh", "Châu", "Dung", "Giang", "Hà", "Hạnh", "Hằng", "Hoa", "Hương", "Lan", "Linh", "Mai", "Nga",
          "Ngân", "Nhung", "Oanh", "Phượng", "Quyên", "Thảo", "Trang", "Uyên", "Vy", "Yến"]
# city -> (CCCD province code, districts, streets)
CITIES = {
    "Hà Nội": ("001", ["Ba Đình", "Hoàn Kiếm", "Đống Đa", "Cầu Giấy", "Thanh Xuân", "Hai Bà Trưng", "Long Biên",
                       "Hoàng Mai", "Nam Từ Liêm", "Tây Hồ"],
               ["Kim Mã", "Láng", "Trần Duy Hưng", "Nguyễn Trãi", "Xuân Thủy", "Hoàng Quốc Việt", "Giải Phóng",
                "Lạc Long Quân", "Nguyễn Chí Thanh", "Minh Khai"]),
    "TP. Hồ Chí Minh": ("079", ["Quận 1", "Quận 3", "Quận 7", "Quận 10", "Bình Thạnh", "Phú Nhuận", "Tân Bình",
                                "Gò Vấp", "Thủ Đức", "Tân Phú"],
                        ["Nguyễn Văn Cừ", "Cách Mạng Tháng Tám", "Lê Văn Sỹ", "Phan Xích Long", "Điện Biên Phủ",
                         "Nguyễn Thị Minh Khai", "Hoàng Văn Thụ", "Quang Trung", "Võ Văn Ngân", "Lũy Bán Bích"]),
    "Đà Nẵng": ("048", ["Hải Châu", "Thanh Khê", "Sơn Trà", "Ngũ Hành Sơn", "Liên Chiểu", "Cẩm Lệ"],
                ["Nguyễn Văn Linh", "Lê Duẩn", "Hàm Nghi", "Trần Phú", "Ngô Quyền", "Tôn Đức Thắng"]),
    "Hải Phòng": ("031", ["Lê Chân", "Ngô Quyền", "Hồng Bàng", "Hải An", "Kiến An"],
                  ["Lạch Tray", "Văn Cao", "Tô Hiệu", "Lê Lợi", "Trần Nguyên Hãn"]),
    "Cần Thơ": ("092", ["Ninh Kiều", "Bình Thủy", "Cái Răng"], ["30 Tháng 4", "Mậu Thân", "Trần Hưng Đạo"]),
    "Bình Dương": ("074", ["Thủ Dầu Một", "Dĩ An", "Thuận An"], ["Đại lộ Bình Dương", "Yersin", "Phú Lợi"]),
}
BANKS = ["Vietcombank", "BIDV", "VietinBank", "Agribank", "Techcombank", "MB Bank", "ACB", "VPBank", "Sacombank", "TPBank"]
COMPANY_WORDS = ["Thương mại Dịch vụ", "Đầu tư Phát triển", "Công nghệ", "Xây dựng", "Tư vấn", "Xuất nhập khẩu"]
COMPANY_NAMES = ["Minh Phát", "An Khang", "Hưng Thịnh", "Sao Việt", "Đại Dương", "Phúc Lộc", "Tân Tiến", "Hoà Bình",
                 "Thiên Long", "Bắc Nam", "Nhật Quang", "Việt Á"]
# property kind -> (title keywords, monthly rent range in million VND)
KINDS = [
    ("văn phòng", ("văn phòng", "trụ sở"), (15, 80)),          # before "phòng"
    ("phòng trọ", ("trọ", "phòng", "sinh viên", "công nhân"), (1.5, 5)),
    ("căn hộ chung cư", ("căn hộ", "chung cư"), (6, 25)),
    ("nhà kinh doanh / mặt bằng", ("kinh doanh", "mặt bằng"), (15, 60)),
    ("nhà xưởng / kho", ("xưởng", "kho"), (30, 150)),
    ("đất / quyền sử dụng đất", ("đất", "quyền sử dụng"), (10, 100)),
    ("biệt thự", ("biệt thự",), (40, 120)),
    ("nhà ở nguyên căn", ("nhà",), (7, 30)),
]


def _person(rng: random.Random, city: str) -> dict:
    male = rng.random() < 0.5
    name = " ".join([rng.choice(HO), rng.choice(DEM_NAM if male else DEM_NU), rng.choice(TEN_NAM if male else TEN_NU)])
    birth = rng.randint(1962, 2003)
    code, districts, streets = CITIES[city]
    century = ("0" if birth < 2000 else "2") if male else ("1" if birth < 2000 else "3")
    issued = rng.randint(max(2021, birth + 14), 2025)
    return {"ho_ten": name, "gioi_tinh": "Nam" if male else "Nữ", "nam_sinh": birth,
            "cccd": f"{code}{century}{birth % 100:02d}{rng.randint(0, 999999):06d}",
            "ngay_cap_cccd": f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{issued}",
            "noi_cap": "Cục Cảnh sát quản lý hành chính về trật tự xã hội",
            "dia_chi": f"Số {rng.randint(1, 300)} đường {rng.choice(streets)}, {rng.choice(districts)}, {city}",
            "dien_thoai": "0" + rng.choice(["9", "8", "3", "7"]) + "".join(str(rng.randint(0, 9)) for _ in range(8)),
            "tai_khoan": f"{rng.randint(10**9, 10**13 - 1)} tại {rng.choice(BANKS)}"}


def _company(rng: random.Random, city: str) -> dict:
    rep = _person(rng, city)
    return {"ten": f"Công ty TNHH {rng.choice(COMPANY_WORDS)} {rng.choice(COMPANY_NAMES)}",
            "ma_so_thue": f"0{rng.randint(100000000, 999999999)}", "dia_chi_tru_so": rep.pop("dia_chi"),
            "nguoi_dai_dien": rep["ho_ten"], "chuc_vu": rng.choice(["Giám đốc", "Tổng Giám đốc"]),
            "dien_thoai": rep["dien_thoai"], "tai_khoan": rep["tai_khoan"]}


def make_profile(title: str, seed: int) -> dict:
    rng = random.Random(seed)
    t = title.lower()
    kind, _, (lo, hi) = next((k for k in KINDS if any(w in t for w in k[1])), KINDS[-1])   # e.g. "bất động sản"
    city = rng.choice(list(CITIES))
    company_ok = kind not in ("phòng trọ",)
    lessor = _company(rng, city) if company_ok and rng.random() < 0.3 else _person(rng, city)
    lessee = (_company(rng, city) if ("công ty" in t or "trụ sở" in t or kind == "văn phòng" or
                                      (company_ok and rng.random() < 0.3)) else _person(rng, city))
    rent = round(rng.uniform(lo, hi) * 2) / 2 * 1_000_000
    day, month, year = rng.randint(1, 28), rng.randint(1, 12), rng.choice([2025, 2026])
    code, districts, streets = CITIES[city]
    return {
        "loai_tai_san": kind, "thanh_pho": city,
        "dia_chi_tai_san": f"Số {rng.randint(1, 500)} đường {rng.choice(streets)}, {rng.choice(districts)}, {city}",
        "dien_tich_m2": {"phòng trọ": rng.randint(12, 30), "căn hộ chung cư": rng.randint(45, 120)}.get(
            kind, rng.randint(40, 400)),
        "ben_cho_thue": lessor, "ben_thue": lessee,
        "gia_thue_thang_vnd": int(rent),
        "tien_coc_so_thang": rng.choice([1, 1, 2, 2, 3]),
        "thoi_han_thang": rng.choice([6, 12, 12, 12, 24, 36]) if kind != "phòng trọ" else rng.choice([3, 6, 6, 12]),
        "ngay_ky": f"{day:02d}/{month:02d}/{year}",
        "ky_thanh_toan": rng.choice(["hàng tháng", "hàng tháng", "3 tháng một lần", "6 tháng một lần"]),
        "han_thanh_toan": f"trước ngày {rng.choice([5, 5, 10, 15])} của kỳ thanh toán",
        "phuong_thuc_thanh_toan": rng.choice(["chuyển khoản", "chuyển khoản", "tiền mặt"]),
        "dien_nuoc": rng.choice(["theo chỉ số công tơ, giá nhà nước", "điện 3.500 đ/kWh, nước 100.000 đ/người/tháng",
                                 "bên thuê tự thanh toán theo hóa đơn của nhà cung cấp"]),
    }


# ---------------- prompt ----------------

PROMPT = """Bạn điền một mẫu hợp đồng thuê thành một hợp đồng hoàn chỉnh, hư cấu, dùng làm dữ liệu thử nghiệm.

Quy tắc:
1. Giữ NGUYÊN VĂN mọi chữ của mẫu, đúng thứ tự: không sửa câu chữ, không xóa, không thêm hay bỏ điều khoản, không sửa lỗi chính tả của mẫu.
2. Điền MỌI chỗ trống: dấu chấm "....", "…", gạch "___", chỗ trống sau dấu hai chấm, và các chỉ dẫn trong ngoặc như "(ĐIỀN HỌ TÊN)" (thay chỉ dẫn bằng nội dung). Mẫu bị lỗi định dạng: một dấu chấm đứng lẻ giữa các chữ ("ngõ . đường", "phường .,") cũng là chỗ trống; nhãn thiếu hẳn giá trị (ví dụ "Ông CMTND số" thiếu tên sau "Ông") thì chèn giá trị vào đúng chỗ.
3. Dùng các thông tin trong HỒ SƠ bên dưới. Thông tin hồ sơ không có thì tự đặt cho hợp lý và nhất quán (ngày tháng, số tiền bằng chữ khớp với bằng số, ngày cấp sau ngày sinh...).
4. Chỗ mẫu để trống cho các bên tự thỏa thuận (ví dụ "Do các bên thỏa thuận:" mà không có nội dung) thì viết nội dung ngắn gọn, công bằng cho cả hai bên, đúng pháp luật Việt Nam.
5. Ô lựa chọn hoặc phương án "hoặc" thì chọn một phương án phù hợp hồ sơ, giữ nguyên chữ của mẫu.
6. Chỉ in ra toàn văn hợp đồng đã điền. Không giải thích, không markdown, không dùng ** hay #.

HỒ SƠ:
{profile}

MẪU HỢP ĐỒNG:
{template}"""

RETRY = """

LƯU Ý: một lần điền trước đã sửa hoặc xóa chữ của mẫu ở các chỗ sau (mẫu -> bản đã điền). Lần này giữ nguyên chữ của
mẫu ở các chỗ đó, chỉ điền chỗ trống:
{violations}"""


# ---------------- checks ----------------

TOKEN = re.compile(r"\w+|[^\w\s]")
BLANKISH = re.compile(r"[.…_\-–—/:;,()\[\]*]+|[xX]{2,}")
LEFTOVER = re.compile(r"\.{3,}|…{2,}|_{3,}|\([^()]*\bĐIỀN\b[^()]*\)|(?<=\s)\.(?=\s*[\w,(])")   # last: lone-dot blank


def tokens(s: str) -> list[tuple[str, int, int]]:
    return [(m.group(), m.start(), m.end()) for m in TOKEN.finditer(s)]


def _placeholder_mask(text: str, toks) -> list[bool]:
    """True for template tokens inside an all-caps parenthetical, e.g. (ĐIỀN ĐẦY ĐỦ HỌ VÀ TÊN)."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"\(([^()]{3,80})\)", text)
             if (lambda s: s.upper() == s and any(c.isalpha() for c in s))(m.group(1))]
    return [any(a <= s < b for a, b in spans) for _, s, _ in toks]


def compare(template: str, filled: str) -> dict:
    """-> {"violations": [{template, filled, lost_words}], "inserted": [[start, end]] in filled}"""
    a, b = tokens(template), tokens(filled)
    ph = _placeholder_mask(template, a)
    sm = difflib.SequenceMatcher(None, [t for t, _, _ in a], [t for t, _, _ in b], autojunk=False)
    violations, inserted = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        new = [b[j][0] for j in range(j1, j2)]
        lost = [a[i][0] for i in range(i1, i2) if not BLANKISH.fullmatch(a[i][0]) and not ph[i]
                and not any(n != a[i][0] and n.startswith(a[i][0]) for n in new)]    # "năm 20.." -> "2026"
        if lost:
            violations.append({"template": " ".join(t for t, _, _ in a[i1:i2])[:120],
                               "filled": " ".join(new)[:120], "lost_words": len(lost)})
        if j2 > j1:
            inserted.append([b[j1][1], b[j2 - 1][2]])
    return {"violations": violations, "inserted": inserted}


# ---------------- one variant ----------------

def server_cfg(base_url: str) -> dict:
    return {"default_profile": "fill", "profiles": {"fill": {
        "base_url": base_url, "model": "local", "timeout_s": 1800, "retries": 2,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}}}


def lost(c: dict) -> int:
    return sum(v["lost_words"] for v in c["cmp"]["violations"])


def party_names(profile: dict) -> list[str]:
    return [p.get("ten") or p["ho_ten"] for p in (profile["ben_cho_thue"], profile["ben_thue"])]


def fill_one(tpl: dict, k: int, cfg: dict, out_dir: Path, temperature: float = 0.6) -> dict:
    name = Path(tpl["file"]).stem
    seed = int(hashlib.sha256(f"{name}:{k}".encode()).hexdigest()[:8], 16)
    profile = make_profile(tpl["title"], seed)
    template = ingest(TEMPLATES / tpl["file"]).text
    n_tok = len(template) / 3.6
    sampling = {"temperature": temperature, "max_tokens": int(min(16000, n_tok * 1.6 + 1500))}
    prompt = PROMPT.format(profile=json.dumps(profile, ensure_ascii=False, indent=1), template=template)
    attempts, best, note = [], None, ""
    t0 = time.monotonic()
    for attempt in range(2):
        # a retry is a fresh request with the corrections appended, not a follow-up turn: the first answer in the
        # history would double the prompt and overflow the slot on long templates
        r = llm.chat("synth_fill", [{"role": "user", "content": prompt + note}], sampling=sampling, cfg=cfg)
        filled = ingest(r.text.strip().encode("utf-8"), "filled.txt").text
        cand = {"filled": filled, "cmp": compare(template, filled), "finish": r.finish_reason,
                "leftover": [m.group() for m in LEFTOVER.finditer(filled)],
                "missing_parties": [n for n in party_names(profile) if n not in filled]}
        attempts.append({"finish": r.finish_reason, "usage": r.usage, "seconds": r.seconds, "lost_words": lost(cand),
                         "leftover": len(cand["leftover"]), "missing_parties": len(cand["missing_parties"])})
        rank = lambda c: (c["finish"] != "stop", lost(c), len(c["missing_parties"]), len(c["leftover"]))
        if best is None or rank(cand) < rank(best):
            best = cand
        if rank(best) == (False, 0, 0, 0):
            break
        if cand["finish"] != "stop":
            note = ""                                  # cut off: nothing useful to quote, just try again
        else:
            note = RETRY.format(violations="\n".join(
                f"- «{v['template']}» -> «{v['filled']}»" for v in cand["cmp"]["violations"][:25]) or "- (không có)")
            if cand["missing_parties"] or cand["leftover"]:
                note += "\nNgoài ra phải điền đủ tên các bên và mọi chỗ trống."
    v = best["cmp"]["violations"]
    flags = [f for f, hit in (("truncated", best["finish"] != "stop"), ("lost_words", v),
                              ("leftover_blanks", best["leftover"]), ("missing_parties", best["missing_parties"])) if hit]
    status = "flagged" if flags else "ok"
    meta = {"template": tpl["file"], "title": tpl["title"], "variant": k, "seed": seed, "temperature": temperature, "status": status,
            "flags": flags, "profile": profile, "violations": v, "leftover_blanks": best["leftover"],
            "missing_parties": best["missing_parties"],
            "inserted": best["cmp"]["inserted"], "template_chars": len(template), "filled_chars": len(best["filled"]),
            "attempts": attempts, "seconds": round(time.monotonic() - t0, 1),
            "text_sha256": hashlib.sha256(best["filled"].encode()).hexdigest()}
    out_dir = out_dir / status
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}_v{k}.txt").write_text(best["filled"], encoding="utf-8")
    (out_dir / f"{name}_v{k}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variants", type=int, default=5)
    ap.add_argument("--only", help="comma-separated template ids, e.g. 24,60")
    ap.add_argument("--workers", type=int, default=4, help="requests in flight; match llama-server --parallel")
    ap.add_argument("--limit", type=int, help="stop after this many variants (pilot runs)")
    ap.add_argument("--base-url", default="http://127.0.0.1:9876/v1")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--temperature", type=float, default=0.6)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    a.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((TEMPLATES / "manifest.json").read_text(encoding="utf-8"))
    manifest = [t for t in manifest if t["id"] not in PREFILLED and t["id"] not in DUPLICATE_OF]
    if a.only:
        ids = set(a.only.split(","))
        manifest = [t for t in manifest if t["id"] in ids]
    jobs = [(t, k) for t in manifest for k in range(1, a.variants + 1)
            if not any((a.out / d / f"{Path(t['file']).stem}_v{k}.json").exists() for d in ("ok", "flagged"))]
    jobs.sort(key=lambda j: -j[0]["chars"])          # longest first: the slow ones do not trail at the end
    jobs = jobs[:a.limit] if a.limit else jobs
    log.info("%d variants to fill, %d workers", len(jobs), a.workers)
    cfg, done, counts, t0 = server_cfg(a.base_url), 0, {}, time.monotonic()
    with ThreadPoolExecutor(a.workers) as pool:
        futs = {pool.submit(fill_one, t, k, cfg, a.out, a.temperature): (t, k) for t, k in jobs}
        for f in as_completed(futs):
            t, k = futs[f]
            done += 1
            try:
                m = f.result()
                counts[m["status"]] = counts.get(m["status"], 0) + 1
                log.info("[%d/%d] %s v%d: %s, %d lost words, %d leftover, %d missing parties, %.0fs", done, len(jobs),
                         t["file"], k, "/".join([m["status"]] + m["flags"]), sum(v["lost_words"] for v in m["violations"]),
                         len(m["leftover_blanks"]), len(m["missing_parties"]), m["seconds"])
            except Exception as e:                   # one bad variant must not stop the batch
                counts["error"] = counts.get("error", 0) + 1
                log.warning("[%d/%d] %s v%d failed: %s", done, len(jobs), t["file"], k, e)
    log.info("done in %.0f min: %s", (time.monotonic() - t0) / 60, counts)


if __name__ == "__main__":
    main()
