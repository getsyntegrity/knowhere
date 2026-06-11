"""FileAdapter contract for converting provider-specific file data into canonical File entities.

This contract is abstract — implementation is part of KNOW-003 Parsing & Symbol Extraction
and provider-specific adapters (Knowhere, Mem0, Atlas Native, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any, Iterable


class FileAdapter(ABC):
    """Converts provider-specific file representations into canonical File entities.

    Contract requirements from spec §8.2:
    - MUST derive a deterministic id from the file's path and repository origin
    - MUST compute a content checksum using the configured hash algorithm
    - MUST extract or infer language from available provider metadata; fall back to "unknown"
    - MUST populate path as a relative path within the repository
    - MUST populate metadata with any provider-specific attributes that do not map to canonical fields
    - MUST NOT populate symbols, chunks, or references (those are populated by other adapters)
    """

    @abstractmethod
    def to_canonical(self, provider_input: Any, repository_id: str) -> Iterable["File"]:
        """Convert provider-specific input into one or more canonical File entities.

        Args:
            provider_input: Provider-specific file data (e.g., file system path + content,
                database record, API response).
            repository_id: The canonical Repository.id this file belongs to.

        Returns:
            An iterable of canonical File entities.

        Raises:
            ValueError: If the input cannot be converted due to invariant violations.
        """
        ...
