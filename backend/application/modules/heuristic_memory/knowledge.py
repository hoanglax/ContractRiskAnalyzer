"""Versioned knowledge records and validation against the runtime risk taxonomy."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from application.modules.taxonomy import taxonomy

DEFAULT_JSON = taxonomy.REPO / "data" / "heuristics" / "vn_residential_rental.json"
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Phrase = Annotated[Text, Field(pattern=r"\w")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")]
Version = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")]
Checklist = Annotated[tuple[Text, ...], Field(min_length=1)]
PhraseGroup = Annotated[tuple[Phrase, ...], Field(min_length=1)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Provenance(Record):
    origin: Literal["ai_authored", "human_authored"]
    source: Text
    status: Literal["draft", "pending_review", "approved", "retired"]
    reviewer: Text | None = None

    @model_validator(mode="after")
    def check_approval(self):
        if self.status == "approved" and self.reviewer is None:
            raise ValueError("approved records require a reviewer")
        return self


class VerifiedLegalRule(Record):
    """Editorially verified statute metadata, reserved for a separate legal workflow."""

    kind: Literal["verified_legal_rule"]
    id: Slug
    law_id: Slug
    article: Annotated[int, Field(gt=0)]
    official_source: Text
    rule_text: Text
    verified_by: Text


class Example(Record):
    kind: Literal["illustrative_scenario", "linguistic_pattern"]
    text: Text
    status: Literal["draft", "pending_review", "approved"]


class Heuristic(Record):
    kind: Literal["reasoning_heuristic"]
    id: Slug
    domain: Slug
    version: Version
    title: Text
    description: Text
    risk_codes: tuple[Text, ...] = ()
    categories: tuple[Text, ...] = ()
    vocabulary: tuple[Phrase, ...]
    # Each group is OR. All trigger groups must match. Any exclusion phrase vetoes.
    triggers: Annotated[tuple[PhraseGroup, ...], Field(min_length=1)]
    exclusions: tuple[Phrase, ...]
    required_context: Checklist
    cross_clause_checks: Checklist
    reasoning_checklist: Checklist
    expected_behavior: Text
    provenance: Provenance
    examples: tuple[Example, ...] = ()
    legal_reference_ids: tuple[Slug, ...] = ()

    @model_validator(mode="after")
    def check_scope(self):
        if not (self.risk_codes or self.categories):
            raise ValueError("at least one risk code or category is required")
        if self.provenance.status == "approved" and any(e.status != "approved" for e in self.examples):
            raise ValueError("approved heuristics require all attached examples to be approved")
        return self


class KnowledgeBase(Record):
    schema_version: Literal["1.0.0"]
    version: Version
    heuristics: tuple[Heuristic, ...]
    legal_rules: tuple[VerifiedLegalRule, ...] = ()

    @model_validator(mode="after")
    def check_links(self):
        ids = [record.id for record in (*self.heuristics, *self.legal_rules)]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate record ID")
        legal_ids = {rule.id for rule in self.legal_rules}
        for heuristic in self.heuristics:
            unknown = set(heuristic.legal_reference_ids) - legal_ids
            if unknown:
                raise ValueError(f"{heuristic.id}: unknown verified legal rule IDs {sorted(unknown)}")
        return self


def load(path: Path = DEFAULT_JSON, *, tax: taxonomy.Taxonomy | None = None) -> KnowledgeBase:
    knowledge = KnowledgeBase.model_validate_json(Path(path).read_bytes())
    tax = tax if tax is not None else taxonomy.load()
    categories = {group["code"] for group in tax.groups}
    for heuristic in knowledge.heuristics:
        unknown_codes = set(heuristic.risk_codes) - tax.by_code.keys()
        unknown_categories = set(heuristic.categories) - categories
        if unknown_codes or unknown_categories:
            raise ValueError(
                f"{heuristic.id}: unknown taxonomy codes {sorted(unknown_codes)} "
                f"or categories {sorted(unknown_categories)}"
            )
    return knowledge
