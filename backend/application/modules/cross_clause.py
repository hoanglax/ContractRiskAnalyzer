"""Resolve explicit Vietnamese contract references against the active clause map."""

from dataclasses import dataclass
import re
from typing import Literal

from application.modules.context_packet import ClauseReferences
from application.modules.short_term_memory import IndexedClause, RunClauseIndex, RunScope


RelationType = Literal["article", "paragraph", "appendix"]
_NUMBER = r"(?:[0-9]{1,3}|(?-i:[IVXLCDM]{1,8}))"
_NUMBER_END = r"(?![\w/]|[.,–—-][ \t]*[0-9])"
_GAP = r"[^\S\r\n]*(?:\r?\n[^\S\r\n]*)?"
_SEP = r"(?:[^\S\r\n]+|[^\S\r\n]*\r?\n[^\S\r\n]*)"
_HEADING = re.compile(
    rf"^[ \t]*(?P<kind>điều|phụ[ \t]+lục)[ \t]*(?:số[ \t]+)?"
    rf"(?P<number>{_NUMBER}){_NUMBER_END}(?=$|[ \t.:;)–—-])",
    re.IGNORECASE,
)
_MENTION = re.compile(
    rf"\b(?:theo(?:{_SEP}quy{_SEP}định{_SEP}tại)?|quy{_SEP}định{_SEP}tại"
    rf"|tham{_SEP}chiếu|xem){_SEP}"
    rf"(?:khoản{_SEP}(?P<paragraph>[0-9]{{1,3}}){_SEP}điều{_GAP}(?P<parent>{_NUMBER})"
    rf"|điều{_GAP}(?P<article>{_NUMBER})"
    rf"|phụ{_SEP}lục{_GAP}(?:số{_SEP})?(?P<appendix>{_NUMBER})){_NUMBER_END}",
    re.IGNORECASE,
)
_UNSUPPORTED_SUFFIX = re.compile(
    rf"{_GAP}(?:"
    rf"(?:của{_SEP})?(?:bộ{_SEP}luật|luật|nghị{_SEP}định|thông{_SEP}tư|"
    rf"văn{_SEP}bản|hợp{_SEP}đồng{_SEP}số)\b"
    rf"|(?:[,/–—-]|(?:và|hoặc|đến|tới)\b){_GAP}"
    rf"(?:(?:điều|khoản|phụ{_SEP}lục){_SEP})?{_NUMBER}{_NUMBER_END})",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


@dataclass(frozen=True, slots=True)
class ClauseRelation:
    source_clause_id: str
    target_clause_id: str
    relation_type: RelationType
    matching_text: str
    reason: str
    priority: int
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    embedded_heading_span: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class UnresolvedReference:
    source_clause_id: str
    matching_text: str
    source_start: int
    source_end: int
    reason: str


@dataclass(frozen=True, slots=True)
class CrossClauseResult:
    relations: tuple[ClauseRelation, ...]
    references: ClauseReferences
    unresolved: tuple[UnresolvedReference, ...] = ()
    limited: tuple[ClauseRelation, ...] = ()


def _number(token: str) -> int | None:
    if token.isascii() and token.isdecimal():
        return int(token) or None
    if not _ROMAN.fullmatch(token):
        return None
    values = [_ROMAN_VALUES[letter] for letter in token]
    return sum(-value if value < next_value else value
               for value, next_value in zip(values, values[1:] + [0]))


def _heading_key(line: str) -> tuple[str, int] | None:
    match = _HEADING.match(line)
    if match is None or _UNSUPPORTED_SUFFIX.match(line, match.end()):
        return None
    number = _number(match["number"])
    if number is None:
        return None
    kind = "article" if match["kind"].lower() == "điều" else "appendix"
    return kind, number


def _embedded_appendices(clause: IndexedClause):
    """Yield headings in a containing clause without creating new clause IDs."""
    for line in re.finditer(r"(?m)^[^\r\n]+", clause.text):
        if line.start() == 0:
            continue
        match = _HEADING.match(line.group())
        if match is None or match["kind"].lower() == "điều":
            continue
        # A body sentence beginning with "Phụ lục 1 ..." is not enough.
        suffix = line.group()[match.end():].lstrip()
        if suffix and suffix[0] not in ":.–—-":
            continue
        key = _heading_key(line.group())
        if key is not None:
            yield key, (clause.start + line.start(), clause.start + line.end())


def _has_unique_paragraph(clause: IndexedClause, article: int, paragraph: int) -> bool:
    # Verify markers inside the existing article. The packet still receives the article ID.
    number = rf"0*{paragraph}"
    marker = re.compile(
        rf"^[ \t]*(?:khoản[ \t]+{number}(?:[ \t]*[.:)–—-]|$)"
        rf"|(?:0*{article}\.)?{number}[.)])(?=[ \t]|$)",
        re.IGNORECASE,
    )
    count = 0
    for line in clause.text.splitlines()[1:]:
        key = _heading_key(line)
        if key is not None and key[0] == "appendix":
            break
        if marker.match(line):
            count += 1
    return count == 1


def retrieve_cross_clause(
    index: RunClauseIndex, scope: RunScope, source_clause_id: str, *, top_k: int = 3,
) -> CrossClauseResult:
    """Return up to top_k distinct targets of explicit references in the source clause."""
    if type(top_k) is not int or top_k < 0:
        raise ValueError("top_k must be a nonnegative integer")
    source = index.by_id(scope, source_clause_id)
    if source is None or top_k == 0:
        return CrossClauseResult((), index.to_references(scope, ()))

    mentions = tuple(_MENTION.finditer(source.text))
    if not mentions:
        return CrossClauseResult((), index.to_references(scope, ()))
    targets: dict[tuple[str, int], list[tuple[IndexedClause, tuple[int, int] | None]]] = {}
    for clause in index.clauses(scope):
        key = _heading_key(clause.text.partition("\n")[0])
        if key is not None:
            targets.setdefault(key, []).append((clause, None))
        for appendix_key, heading_span in _embedded_appendices(clause):
            targets.setdefault(appendix_key, []).append((clause, heading_span))

    relations = []
    unresolved = []
    for mention in mentions:
        relation: RelationType
        if _UNSUPPORTED_SUFFIX.match(source.text, mention.end()):
            unresolved.append(_unresolved(source, mention, "unsupported_reference"))
            continue
        if mention["parent"]:
            relation, kind, token = "paragraph", "article", mention["parent"]
        elif mention["article"]:
            relation, kind, token = "article", "article", mention["article"]
        else:
            relation, kind, token = "appendix", "appendix", mention["appendix"]
        number = _number(token)
        if number is None:
            unresolved.append(_unresolved(source, mention, "invalid_reference_number"))
            continue
        candidates = targets.get((kind, number), ())
        if len(candidates) != 1:
            reason = "ambiguous_target" if candidates else "missing_target"
            unresolved.append(_unresolved(source, mention, reason))
            continue
        target, embedded_span = candidates[0]
        if target.clause_id == source_clause_id:
            unresolved.append(_unresolved(source, mention, "self_reference"))
            continue
        priority = 1
        reason = "Dẫn chiếu khớp với một tiêu đề được lập chỉ mục."
        if embedded_span is not None:
            reason = "Dẫn chiếu khớp với tiêu đề Phụ lục duy nhất trong điều khoản đích."
        if relation == "paragraph":
            paragraph = _number(mention["paragraph"])
            if paragraph is None or not _has_unique_paragraph(target, number, paragraph):
                unresolved.append(_unresolved(source, mention, "missing_or_ambiguous_paragraph"))
                continue
            priority = 2
            reason = "Dẫn chiếu khớp với một Điều và một dấu đầu dòng Khoản duy nhất trong Điều đó."
        relations.append(ClauseRelation(
            source_clause_id, target.clause_id, relation, mention.group(), reason, priority,
            source.start + mention.start(), source.start + mention.end(), target.start, target.end, embedded_span,
        ))

    ranked = sorted(relations, key=lambda item: (-item.priority, item.source_start, item.target_start))
    unique: dict[str, ClauseRelation] = {}
    for relation in ranked:
        unique.setdefault(relation.target_clause_id, relation)
    ranked = tuple(unique.values())
    selected = ranked[:top_k]
    return CrossClauseResult(
        selected, index.to_references(scope, (edge.target_clause_id for edge in selected)),
        tuple(unresolved), ranked[top_k:],
    )


def _unresolved(source: IndexedClause, mention: re.Match, reason: str) -> UnresolvedReference:
    return UnresolvedReference(
        source.clause_id, mention.group(), source.start + mention.start(), source.start + mention.end(), reason,
    )
