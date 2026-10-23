"""What the rest of the system needs from the statute store. Implementations are swappable: today
SQLite FTS5 (+ a numpy matrix for vectors), later Qdrant or pgvector if scale or filtering ever
demands it. Callers depend on this protocol only."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Hit:
    chunk_id: int
    article_id: int
    law: str                 # corpus file stem, e.g. "luat_nha_o_2023"
    dieu_no: int | None
    ref: str                 # khoản / điểm within the Điều ("" = whole article)
    score: float             # higher is better
    text: str                # heading + the unit


class Retriever(Protocol):
    def search(self, query: str, k: int = 5, law: str | None = None) -> list[Hit]: ...
