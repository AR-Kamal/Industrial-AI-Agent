"""Provider-neutral document retrieval contract.

Milestone 1 defines the boundary only. It performs no retrieval or indexing.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RetrievedDocument:
    source_id: str
    title: str
    excerpt: str


class DocumentRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> Sequence[RetrievedDocument]:
        """Return approved evidence for a query."""

        ...
