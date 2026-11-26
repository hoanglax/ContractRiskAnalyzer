"""Vietnamese rental-specific eligibility and supporting lexical evidence."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.casefold())
    return " " + " ".join(re.findall(r"\w+", text)) + " "


# Keep negative obligations such as "không hoàn cọc" as explicit phrases.
# Suppress bare positive mentions when directly negated or merely disclaimed.
_NEGATED = re.compile(
    r"\b(?:không|chưa)(?: (?:bị|được|phải|cần|có|sẽ|áp dụng|chịu|đề cập|quy định|"
    r"điều khoản|về|việc|bên nào|bắt buộc)){0,6} $"
)


@dataclass(frozen=True)
class Passage:
    id: str
    text: str

    def find(self, phrases, *, positive=True):
        found = set()
        for phrase in phrases:
            token = normalize(phrase)
            if any(
                not positive or not _NEGATED.search(self.text[:match.start() + 1])
                for match in re.finditer(re.escape(token), self.text)
            ):
                found.add(phrase)
        return found

    def has(self, *phrases):
        return bool(self.find(phrases, positive=False))


@dataclass(frozen=True)
class Rule:
    # Extra alternatives, keyed by the original trigger group index.
    aliases: tuple[tuple[str, ...], ...] = ()
    required: tuple[tuple[str, ...], ...] = ()
    distractors: tuple[str, ...] = ()
    linked: tuple[tuple[str, ...], ...] = ()


_RENT = ("giá thuê", "tiền thuê", "tiền nhà", "mức thuê")
_LEASE = ("hợp đồng", "thuê", "căn hộ", "kỳ thuê", "thời hạn thuê")
_FEES = ("phí quản lý", "phí dịch vụ", "phí vận hành", "tiền điện", "tiền nước", "phí gửi xe")
_HANDOVER = ("chìa khóa", "chìa khoá", "thẻ ra vào", "công tơ", "biên bản", "chậm bàn giao")
_MOVE_OUT = ("trả nhà", "trả căn hộ", "dọn ra", "bàn giao lại", "thu hồi nhà",
             "hết hạn", "chấm dứt", "thanh lý", "kết thúc kỳ thuê")
_PREEXISTING = ("lúc nhận", "khi nhận", "đầu kỳ", "ban đầu", "có sẵn", "từ trước", "trước khi thuê")
_CONDITION = ("vết", "sơn", "trầy", "ố", "bong", "bạc màu", "cũ", "hư hỏng")
_ANNEX = ("phụ lục", "thỏa thuận bổ sung", "thoả thuận bổ sung", "văn bản bổ sung")
_CHANGE = ("ưu tiên áp dụng", "mâu thuẫn", "thay thế", "sửa đổi", "điều chỉnh", "mức mới")
_REMEDY = ("phạt vi phạm", "bồi thường", "lãi chậm trả", "tiền phạt", "khoản phạt")
_OFFSET = ("khấu trừ", "cấn trừ", "trừ vào cọc", "ghi có")


RULES = {
    "deposit_identity": Rule(
        aliases=(("tiền giữ căn", "tiền giữ phòng", "khoản bảo đảm"), ("ứng tiền thuê", "trừ vào tiền thuê")),
        linked=(("tiền giữ chỗ", "tiền giữ căn", "tiền giữ phòng"),),
    ),
    "deposit_refund_clock": Rule(aliases=(("trả cọc", "hoàn lại tiền cọc", "hoàn lại khoản bảo đảm"),)),
    "deposit_deductions": Rule(aliases=(("trừ vào tiền cọc", "khấu trừ vào tiền cọc", "trừ vào khoản bảo đảm"),)),
    "deposit_forfeiture": Rule(
        aliases=(("giữ toàn bộ tiền cọc", "không trả lại tiền cọc", "không trả cọc"),),
        distractors=("thẻ xe", "chỗ đỗ xe", "cọc mua nhà"),
    ),
    "termination_notice_clock": Rule(
        aliases=(("dọn trước hạn", "dọn đi giữa kỳ", "trả nhà trước hạn", "kết thúc hợp đồng",
                  "ngừng thuê trước hạn", "rời nhà trước hạn"),
                 ("gửi thư trước", "gửi văn bản trước", "báo bằng văn bản", "báo cho",
                  "không báo trước")),
        distractors=("hợp đồng vệ sinh", "hợp đồng bảo trì", "hợp đồng dịch vụ"),
    ),
    "renewal_vs_exit": Rule(
        aliases=(("nối tiếp kỳ thuê", "kéo dài thời hạn thuê"),
                 ("đáo hạn", "kỳ hiện tại", "không báo trước")),
        required=(_LEASE + ("tự động gia hạn",),),
        distractors=("bảo hành thẻ", "hiệu lực thẻ", "gia hạn thẻ", "gia hạn bảo hành"),
    ),
    "lessor_identity": Rule(
        aliases=(("người cho thuê",), ("sổ hồng", "sổ đỏ", "đại diện theo ủy quyền")),
        linked=(("giấy chứng nhận", "sổ hồng", "sổ đỏ", "ủy quyền", "uỷ quyền"),),
    ),
    "co_owner_consent": Rule(
        aliases=(("cùng đứng tên", "cùng sở hữu", "đồng đứng tên", "cả hai vợ chồng"),),
        required=(("căn hộ", "căn nhà", "nơi ở", "nhà thuê", "ký", "thuê", "đứng tên"),),
        distractors=("hành lang", "khu vực chung", "sở hữu chung của cư dân"),
    ),
    "sublease_scope": Rule(
        aliases=(("hợp đồng thuê chính", "cho người khác thuê", "cho bên thứ ba thuê"),),
    ),
    "wear_baseline": Rule(
        aliases=(("bạc màu", "hao mòn do sử dụng", "hư hỏng có sẵn"),),
        required=(_MOVE_OUT + _PREEXISTING + _CONDITION,),
        distractors=("xe đạp", "xe máy", "bảng tên"),
    ),
    "repair_reimbursement": Rule(
        aliases=(("gọi thợ", "thuê thợ", "khắc phục sự cố"),
                 ("thanh toán lại", "hoàn lại chi phí", "hoàn tiền sửa", "ứng tiền", "chi trước")),
        required=(("hoàn trả chi phí", "hoàn lại chi phí", "chi phí hợp lý", "khẩn cấp",
                   "thanh toán lại", "hoàn tiền sửa", "ứng tiền", "chi trước"),),
    ),
    "repair_disruption": Rule(
        aliases=(("sửa chữa", "thi công"), ("không thể ở", "không ở được", "mất công năng")),
    ),
    "rent_increase": Rule(
        aliases=(("giá thuê mới", "tiền thuê mới", "nâng mức tiền nhà", "tăng tiền nhà",
                  "tăng tiền thuê", "điều chỉnh tiền thuê", "điều chỉnh tiền nhà"),),
    ),
    "utility_service_fees": Rule(
        aliases=(("phí vận hành", "chi phí điện nước", "tiền điện nước", "phí trông xe"),),
    ),
    "tax_incidence": Rule(
        aliases=(("thuế cho thuê", "thuế thuê nhà", "kê khai thuế"), ("chịu thuế", "trả thay", "kê khai thay")),
        required=(("thuế", "nộp thay", "thuế cho thuê", "thuế thuê nhà", "kê khai thay"),),
    ),
    "overlapping_remedies": Rule(
        aliases=(("tiền phạt", "khoản phạt"), ("trừ vào cọc", "ghi có")),
        required=(_REMEDY,),
    ),
    "return_milestones": Rule(
        aliases=(("trả căn hộ", "bàn giao lại", "giao lại căn hộ"), ("thẻ ra vào", "xác nhận bàn giao")),
        required=(_MOVE_OUT + ("giao lại căn hộ",),),
        linked=(("chìa khóa", "chìa khoá", "thẻ ra vào", "công tơ", "chậm bàn giao"),),
    ),
    "annex_conflict": Rule(aliases=(("văn bản bổ sung",), ("sửa đổi", "mức mới", "phí quản lý", "tiền thuê"))),
}


def evidence(heuristic, passages):
    """Return matched phrases and the passages carrying the trigger evidence."""
    rule = RULES.get(heuristic.id) if heuristic.domain == "vn_residential_rental" else None
    usable = tuple(
        p for p in passages
        if not p.find(heuristic.exclusions, positive=False)
        and not (rule and p.find(rule.distractors, positive=False))
    )
    if not usable:
        return None

    groups = list(heuristic.triggers)
    if rule:
        for i, aliases in enumerate(rule.aliases[:len(groups)]):
            groups[i] += aliases

    # Custom records retain their original conjunctive trigger semantics.
    windows = [usable] if rule is None else [(p,) for p in usable]
    if rule and rule.linked:
        windows.extend(
            (a, b) for a, b in zip(usable, usable[1:])
            if all(a.find(g) or b.find(g) for g in rule.linked)
        )

    best = None
    for window in windows:
        hits = tuple(set().union(*(p.find(g, positive=rule is not None) for p in window))
                     for g in groups)
        if rule and not all(any(p.find(g) for p in window) for g in rule.required):
            continue
        if rule and not valid_context(heuristic.id, window):
            continue
        if not all(hits):
            continue
        vocab = set().union(*(p.find(heuristic.vocabulary, positive=rule is not None)
                              for p in window))
        rank = (len(vocab), -len(window), sum(map(len, hits)))
        if best is None or rank > best[0]:
            best = rank, hits, vocab, window

    if best is None:
        return structural_evidence(heuristic.id, usable) if rule else None
    _, hits, vocab, window = best
    phrase_groups = tuple(tuple(sorted(group)) for group in hits)
    return phrase_groups, tuple(sorted(vocab)), tuple(p.id for p in window)


def valid_context(identifier, window):
    if identifier == "deposit_identity":
        return not any(p.has(*_REMEDY, "quyết toán", "bồi hoàn thiệt hại") for p in window)
    if identifier == "overlapping_remedies":
        p, = window
        remedies = p.find(_REMEDY + ("mất cọc", "không hoàn cọc"))
        return len(remedies) >= 2 or bool(p.find(_OFFSET))
    if identifier == "annex_conflict":
        p, = window
        return bool(p.find(_CHANGE))
    return True


def structural_evidence(identifier, passages):
    """Recognize a few relations that literal phrase alternatives cannot express."""
    for p in passages:
        if identifier == "deposit_refund_clock":
            action = p.find(("chuyển lại", "trả lại", "hoàn lại", "gửi lại"))
            deposit = p.find(("khoản bảo đảm", "tiền bảo đảm", "tiền ký quỹ", "tiền cọc"))
            if action and deposit and p.has("trong vòng", "kể từ", "sau khi", "chậm nhất"):
                return relation((action, deposit), (p,))
        if identifier == "wear_baseline":
            condition = p.find(_CONDITION)
            baseline = p.find(_PREEXISTING)
            if condition and baseline and p.has("ảnh", "biên bản", "tình trạng"):
                for q in passages:
                    cost = q.find(("chi phí", "trừ vào cọc", "khấu trừ", "sơn lại", "sơn mới"))
                    if q is not p and cost and q.has(*_MOVE_OUT) and q.find(_CONDITION):
                        return relation((baseline, condition, cost), (p, q))
        if identifier == "overlapping_remedies":
            offset = p.find(_OFFSET)
            reference = p.find(("khoản phạt đó", "cùng vi phạm", "cùng hành vi", "khoản tiền phạt"))
            if offset and reference:
                for q in passages:
                    remedy = q.find(_REMEDY)
                    if q is not p and remedy:
                        return relation((remedy, offset, reference), (q, p))
        if identifier == "annex_conflict":
            annex = p.find(_ANNEX)
            fields = (_RENT, _FEES, ("tiền cọc", "khoản bảo đảm"), ("thời hạn thuê",))
            if annex:
                for q in passages:
                    if q is p or not q.has("điều", "hợp đồng", "bảng thanh toán"):
                        continue
                    for field in fields:
                        other = q.find(field)
                        current = p.find(field)
                        if field == _FEES and p.has("cùng loại phí", "phí nêu trên"):
                            current = p.find(("cùng loại phí", "phí nêu trên"))
                        if current and other:
                            return relation((annex, current, other), (p, q))
    return None


def relation(groups, passages):
    return tuple(tuple(sorted(group)) for group in groups), (), tuple(p.id for p in passages)
