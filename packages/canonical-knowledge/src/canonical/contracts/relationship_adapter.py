"""
RelationshipAdapter contract for the canonical knowledge model.

This contract defines the interface that all RelationshipAdapters must implement.
RelationshipAdapters are responsible for converting provider-specific relationship 
or graph edge representations into canonical Relationship entities.
"""

from abc import ABC, abstractmethod
from typing import List, Any
from pydantic import BaseModel

from canonical.entities.relationship import Relationship


class RelationshipAdapterContract(ABC):
    """
    Abstract base class defining the RelationshipAdapter contract.
    
    Every RelationshipAdapter MUST:
    - Accept a provider-specific input and return a canonical Relationship entity
    - Validate all invariants of the canonical Relationship entity before returning
    - Fail explicitly with a descriptive error if conversion is not possible
    - Be stateless — given identical input, produce identical output (deterministic)
    - Not modify, cache, or persist the provider's internal data
    """
    
    @abstractmethod
    def convert(self, provider_relationship_data: Any) -> List[Relationship]:
        """
        Convert provider-specific relationship data into canonical Relationship entities.
        
        Args:
            provider_relationship_data: Provider-specific relationship data (e.g., graph edge, 
                                       dependency entry, cross-reference record)
        
        Returns:
            List[Relationship]: One or more canonical Relationship entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical Relationship entities
        """
        pass