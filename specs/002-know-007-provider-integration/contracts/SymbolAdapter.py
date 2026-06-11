"""SymbolAdapter contract for converting provider-specific symbol data into canonical Symbol entities.

This contract is abstract — implementation is part of KNOW-003 Parsing & Symbol Extraction
and provider-specific adapters.
"""

from abc import ABC, abstractmethod
from typing import Any, Iterable


class SymbolAdapter(ABC):
    """Converts provider-specific symbol representations into canonical Symbol entities.

    Contract requirements from spec §8.3:
    - MUST derive deterministic id from symbol qualified_name + repository_id
    - MUST construct qualified_name from provider's hierarchical symbol info
    - MUST map provider symbol kind to canonical kind; use "unknown" if no mapping
    - MUST validate location falls within parent File bounds
    - MUST preserve parent-child hierarchy via children collection
    - MUST NOT include path/file components in qualified_name
    - SHOULD extract documentation from provider docstrings when available
    """

    @abstractmethod
    def to_canonical(self, provider_input: Any, file_id: str, repository_id: str) -> Iterable["Symbol"]:
        """Convert provider-specific input into one or more canonical Symbol entities.

        Args:
            provider_input: Provider-specific symbol data (e.g., AST node, LSP symbol).
            file_id: The canonical File.id this symbol belongs to.
            repository_id: The canonical Repository.id this symbol belongs to.

        Returns:
            An iterable of canonical Symbol entities.

        Raises:
            ValueError: If the input cannot be converted due to invariant violations.
        """
        ...
