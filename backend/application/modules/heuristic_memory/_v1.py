"""Deterministic selection over locally supplied contract text."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from application.modules.taxonomy import taxonomy

from .knowledge import Heuristic, KnowledgeBase


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text.casefold())
    return " " + " ".join(re.findall(r"\w+", text)) + " "


@dataclass(frozen=True)
class Selection:
    heuristic: Heuristic
    knowledge_version: str
    matched_codes: tuple[str, ...]
    matched_categories: tuple[str, ...]
    matched_triggers: tuple[tuple[str, ...], ...]
    matched_vocabulary: tuple[str, ...]

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
        text: str,
        risk_codes: Iterable[str] = (),
        categories: Iterable[str] = (),
        top_k: int = 5,
        include_drafts: bool = False,
    ) -> list[Selection]:
        if type(top_k) is not int or top_k < 0:
            raise ValueError("top_k must be a nonnegative integer")
        if top_k == 0:
            return []
        codes = set(risk_codes)
        groups = set(categories)
        groups.update(self._code_groups[code] for code in codes if code in self._code_groups)
        allowed = {"approved", "draft", "pending_review"} if include_drafts else {"approved"}
        normalized = _normalize(text)

        def matches(phrases: tuple[str, ...]) -> tuple[str, ...]:
            return tuple(sorted({phrase for phrase in phrases if _normalize(phrase) in normalized}))

        candidates = []
        for heuristic in self.knowledge.heuristics:
            if heuristic.domain != domain or heuristic.provenance.status not in allowed:
                continue
            triggers = tuple(matches(group) for group in heuristic.triggers)
            if not all(triggers) or matches(heuristic.exclusions):
                continue
            matched_codes = tuple(sorted(codes.intersection(heuristic.risk_codes)))
            related_groups = set(heuristic.categories)
            related_groups.update(self._code_groups[code] for code in heuristic.risk_codes
                                  if code in self._code_groups)
            candidates.append(Selection(
                heuristic, self.knowledge.version, matched_codes, tuple(sorted(groups & related_groups)),
                triggers, matches(heuristic.vocabulary),
            ))
        return sorted(candidates, key=lambda hit: (
            -len(hit.matched_codes), -len(hit.matched_categories),
            -len(hit.matched_vocabulary), hit.id,
        ))[:top_k]
