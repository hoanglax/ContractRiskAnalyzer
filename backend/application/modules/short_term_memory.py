"""In-memory clause lookup for one analysis and one cleaned document."""

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Literal

from application.modules.context_packet import ClauseReferences, clause_id
from application.modules.ingestion.ingest import Clause, Document


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RunScope:
    run_id: str
    document_sha256: str

    def __post_init__(self):
        # The packet builder accepts opaque run IDs, including offline fixture IDs.
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("Expected a nonempty run ID")
        if not isinstance(self.document_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.document_sha256
        ):
            raise ValueError("Expected a lowercase SHA-256 digest")

    @classmethod
    def for_document(cls, run_id: str, document: Document) -> "RunScope":
        return cls(run_id, _digest(document.text))


@dataclass(frozen=True, slots=True)
class IndexedClause:
    clause_id: str
    label: str
    heading: str
    level: int
    start: int
    end: int
    text: str
    provenance: Literal["clause_map"] = "clause_map"


def _ordered_clauses(document: Document) -> list[Clause]:
    clauses = getattr(document.structure, "clauses", None) or ()
    if any(
        not isinstance(clause, Clause)
        or type(clause.char_start) is not int
        or type(clause.char_end) is not int
        or not 0 <= clause.char_start < clause.char_end <= len(document.text)
        for clause in clauses
    ):
        return []
    ordered = sorted(clauses, key=lambda clause: (clause.char_start, clause.char_end))
    if any(left.char_end > right.char_start for left, right in zip(ordered, ordered[1:])):
        return []
    return ordered


@dataclass(frozen=True, slots=True)
class _ClauseSpan:
    clause_id: str
    label: str
    heading: str
    level: int
    start: int
    end: int

    def excerpt(self, text: str) -> IndexedClause:
        return IndexedClause(
            self.clause_id, self.label, self.heading, self.level,
            self.start, self.end, text[self.start:self.end],
        )


@dataclass(frozen=True, slots=True)
class _IndexData:
    text: str
    spans: tuple[_ClauseSpan, ...]
    starts: tuple[int, ...]
    by_id: dict[str, _ClauseSpan]


class RunClauseIndex:
    """A caller-owned index. Use a context manager to release it on every exit path."""

    def __init__(self, scope: RunScope, document: Document):
        text = document.text
        if scope.document_sha256 != _digest(text):
            raise ValueError("Document text does not match the index scope")
        spans = tuple(
            _ClauseSpan(
                clause_id(clause.char_start, clause.char_end),
                clause.label, clause.heading, clause.level, clause.char_start, clause.char_end,
            )
            for clause in _ordered_clauses(document)
        )
        self._scope = scope
        self._data: _IndexData | None = _IndexData(
            text, spans, tuple(span.start for span in spans),
            {span.clause_id: span for span in spans},
        )

    def __enter__(self) -> "RunClauseIndex":
        self._checked_data(self._scope)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def release(self) -> None:
        """Drop the retained text and index metadata. Repeated calls are harmless."""
        self._data = None

    def _checked_data(self, scope: RunScope) -> _IndexData:
        if scope != self._scope:
            raise ValueError("Run ID or document digest does not match the index scope")
        data = self._data
        if data is None:
            raise RuntimeError("Clause index has been released")
        return data

    def by_id(self, scope: RunScope, identifier: str) -> IndexedClause | None:
        data = self._checked_data(scope)
        span = data.by_id.get(identifier)
        return span.excerpt(data.text) if span is not None else None

    def clauses(self, scope: RunScope) -> tuple[IndexedClause, ...]:
        """Return the indexed clauses in document order."""
        data = self._checked_data(scope)
        return tuple(span.excerpt(data.text) for span in data.spans)

    def source_text(self, scope: RunScope) -> str:
        """Return the immutable cleaned text, including text outside the clause map."""
        return self._checked_data(scope).text

    def at_offset(self, scope: RunScope, offset: int) -> IndexedClause | None:
        data = self._checked_data(scope)
        if type(offset) is not int:
            raise ValueError("Expected an integer source offset")
        position = bisect_right(data.starts, offset) - 1
        if position >= 0 and offset < data.spans[position].end:
            return data.spans[position].excerpt(data.text)
        return None

    def overlapping(self, scope: RunScope, start: int, end: int) -> tuple[IndexedClause, ...]:
        data = self._checked_data(scope)
        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
            raise ValueError("Expected an ordered, nonnegative source span")
        if start == end:
            return ()
        first = max(0, bisect_right(data.starts, start) - 1)
        stop = bisect_left(data.starts, end)
        return tuple(span.excerpt(data.text) for span in data.spans[first:stop] if span.end > start)

    def to_references(self, scope: RunScope, identifiers: Iterable[str]) -> ClauseReferences:
        """Package caller-selected IDs in priority order, rejecting unknown clauses."""
        data = self._checked_data(scope)
        unique: dict[str, None] = {}
        for identifier in identifiers:
            if not isinstance(identifier, str) or identifier not in data.by_id:
                raise ValueError("Clause references contain an unknown clause ID")
            unique[identifier] = None
        return ClauseReferences(scope.run_id, scope.document_sha256, tuple(unique))
