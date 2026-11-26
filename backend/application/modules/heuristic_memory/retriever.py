"""Deterministic selection over locally supplied contract text."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from application.modules.taxonomy import taxonomy

from .knowledge import Heuristic, KnowledgeBase
from .rental_matching import Passage, evidence, normalize


@dataclass(frozen=True)
class Clause:
    id: str
    text: str


@dataclass(frozen=True)
class Selection:
    heuristic: Heuristic
    knowledge_version: str
    matched_codes: tuple[str, ...]
    matched_categories: tuple[str, ...]
    matched_triggers: tuple[tuple[str, ...], ...]
    matched_vocabulary: tuple[str, ...]
    matched_clause_ids: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return self.heuristic.id

    @property
    def version(self) -> str:
        return self.heuristic.version


class HeuristicRetriever:
    def __init__(self, knowledge: KnowledgeBase, *, tax: taxonomy.Taxonomy | None = None):
        self.knowledge = knowledge
        tax = tax if tax is not None else taxonomy.load()
        self._code_groups = {code: risk.group for code, risk in tax.by_code.items()}

    def select(
        self,
        *,
        domain: str,
        text: str | None = None,
        clauses: Iterable[Clause] | None = None,
        risk_codes: Iterable[str] = (),
        categories: Iterable[str] = (),
        top_k: int = 5,
        include_drafts: bool = False,
    ) -> list[Selection]:
        if type(top_k) is not int or top_k < 0:
            raise ValueError("top_k must be a nonnegative integer")
        if (text is None) == (clauses is None):
            raise ValueError("Supply either text or clauses")
        if clauses is None:
            # Bare newlines can be wrapping inside a phrase. Explicit clauses
            # are preferable when a caller has parsed the document structure.
            parts = re.split(r"[!?;]+\s*|\.(?=\s|$)", text)
            clauses = (Clause(f"text-{i}", part) for i, part in enumerate(parts, 1))
        passages = tuple(Passage(clause.id, normalize(clause.text)) for clause in clauses)
        ids = {passage.id for passage in passages}
        if len(ids) != len(passages) or any(not identifier.strip() for identifier in ids):
            raise ValueError("Clause IDs must be nonempty and unique")
        if top_k == 0:
            return []
        codes = set(risk_codes)
        groups = set(categories)
        groups.update(self._code_groups[code] for code in codes if code in self._code_groups)
        allowed = {"approved", "draft", "pending_review"} if include_drafts else {"approved"}
        candidates = []
        for heuristic in self.knowledge.heuristics:
            if heuristic.domain != domain or heuristic.provenance.status not in allowed:
                continue
            match = evidence(heuristic, passages)
            if match is None:
                continue
            triggers, vocabulary, clause_ids = match
            matched_codes = tuple(sorted(codes.intersection(heuristic.risk_codes)))
            related_groups = set(heuristic.categories)
            related_groups.update(self._code_groups[code] for code in heuristic.risk_codes
                                  if code in self._code_groups)
            candidates.append(Selection(
                heuristic, self.knowledge.version, matched_codes, tuple(sorted(groups & related_groups)),
                triggers, vocabulary, clause_ids,
            ))
        return sorted(candidates, key=lambda hit: (
            -len(hit.matched_codes), -len(hit.matched_categories),
            -len(hit.matched_vocabulary), hit.id,
        ))[:top_k]
