"""
SymbolAdapter contract for the canonical knowledge model.

This contract defines the interface that all SymbolAdapters must implement.
SymbolAdapters are responsible for converting provider-specific symbol representations
into canonical Symbol entities.
"""

from abc import ABC, abstractmethod
from typing import List, Any
from pydantic import BaseModel

from canonical.entities.symbol import Symbol
from canonical.value_objects.code_location import CodeLocation


class SymbolAdapterContract(ABC):
    """
    Abstract base class defining the SymbolAdapter contract.
    
    Every SymbolAdapter MUST:
    - Accept a provider-specific input and return a canonical Symbol entity
    - Validate all invariants of the canonical Symbol entity before returning
    - Fail explicitly with a descriptive error if conversion is not possible
    - Be stateless — given identical input, produce identical output (deterministic)
    - Not modify, cache, or persist the provider's internal data
    """
    
    @abstractmethod
    def convert(self, provider_symbol_data: Any) -> List[Symbol]:
        """
        Convert provider-specific symbol data into canonical Symbol entities.
        
        Args:
            provider_symbol_data: Provider-specific symbol data (e.g., tree-sitter AST node, 
                                 LSP symbol, parser output)
        
        Returns:
            List[Symbol]: One or more canonical Symbol entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical Symbol entities
        """
        pass