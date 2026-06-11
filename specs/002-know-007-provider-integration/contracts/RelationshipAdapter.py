"""RelationshipAdapter contract for converting provider-specific relationship data into canonical Relationship entities.

This contract is abstract — implementation is part of KNOW-003 Parsing & Symbol Extraction
and provider-specific adapters.
"""

from abc import ABC, abstractmethod
from typing import Any, Iterable


class RelationshipAdapter(ABC):
    """Converts provider-specific relationship/graph edge representations into canonical Relationship entities.

    Contract requirements from spec §8.5:
    - MUST derive deterministic id from (source_id, target_id, type, repository_id)
    - MUST verify source_id and target_id refer to existing canonical entities
    - MUST map provider relationship type to canonical type; use "provider_name:custom" if no mapping
    - MUST reject duplicate (source_id, target_id, type) tuples within a Repository
    - MAY populate weight or attributes from provider-specific metadata
    """

    @abstractmethod
    def to_canonical(self, provider_input: Any, repository_id: str) -> Iterable["Relationship"]:
        """Convert provider-specific input into one or more canonical Relationship entities.

        Args:
            provider_input: Provider-specific relationship data (e.g., graph edge, dependency entry).
            repository_id: The canonical Repository.id this relationship belongs to.

        Returns:
            An iterable of canonical Relationship entities.

        Raises:
            ValueError: If the input cannot be converted due to invariant violations.
        """
        ...
