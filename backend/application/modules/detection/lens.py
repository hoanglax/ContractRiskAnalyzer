"""Sources of LookFor lists. Each source is an adapter; detectors only ever see LookFor.

The taxonomy is the list the app uses: its codes are the only risks detection can report."""
from __future__ import annotations

from application.modules.detection.finding import LookFor
from application.modules.taxonomy.taxonomy import Taxonomy

TAXONOMY_ROLE = {"A": "lessor", "B": "lessee"}    # the workbook's "Quy ước": A = bên cho thuê, B = bên thuê


def from_taxonomy(tax: Taxonomy) -> list[LookFor]:
    return [LookFor(id=r.code, title=r.name, signs=r.signs, affects=TAXONOMY_ROLE[r.party],
                    meta={"group": r.group, "severity": r.severity, "legal_basis": r.legal_basis,
                          "consequences": r.consequences})
            for r in tax.risks]
