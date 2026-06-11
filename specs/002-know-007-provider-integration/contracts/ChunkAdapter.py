"""ChunkAdapter contract for converting provider-specific chunk data into canonical Chunk entities.

This contract is abstract — implementation is part of KNOW-003 Parsing & Symbol Extraction
and provider-specific adapters.
"""

from abc import ABC, abstractmethod
from typing import Any, Iterable


class ChunkAdapter(ABC):
    """Converts provider-specific chunk representations into canonical Chunk entities.

    Contract requirements from spec §8.4:
    - MUST derive deterministic id from (repository_id, file_id, location)
    - MUST compute checksum from text only
    - MUST compute semantic_hash from text only for cross-provider deduplication
    - MUST validate location falls within parent File bounds
    - MUST assign ordering reflecting chunk position in file
    - MUST map provider chunk type to canonical chunk_type; use "unknown" if no mapping
    - MUST NOT include embedding vectors or provider-specific retrieval scores
    - SHOULD verify chunk text matches source content at specified location
    - MAY populate symbol_ids if symbols can be identified within the chunk
    """

    @abstractmethod
    def to_canonical(self, provider_input: Any, file_id: str, repository_id: str) -> Iterable["Chunk"]:
        """Convert provider-specific input into one or more canonical Chunk entities.

        Args:
            provider_input: Provider-specific chunk data (e.g., KnowledgeChunk, parser segment).
            file_id: The canonical File.id this chunk belongs to.
            repository_id: The canonical Repository.id this chunk belongs to.

        Returns:
            An iterable of canonical Chunk entities.

        Raises:
            ValueError: If the input cannot be converted due to invariant violations.
        """
        ...
