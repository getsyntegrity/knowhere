"""
ChunkAdapter contract for the canonical knowledge model.

This contract defines the interface that all ChunkAdapters must implement.
ChunkAdapters are responsible for converting provider-specific chunk representations
into canonical Chunk entities.
"""

from abc import ABC, abstractmethod
from typing import List, Any
from pydantic import BaseModel

from canonical.entities.chunk import Chunk
from canonical.value_objects.code_location import CodeLocation


class ChunkAdapterContract(ABC):
    """
    Abstract base class defining the ChunkAdapter contract.
    
    Every ChunkAdapter MUST:
    - Accept a provider-specific input and return a canonical Chunk entity
    - Validate all invariants of the canonical Chunk entity before returning
    - Fail explicitly with a descriptive error if conversion is not possible
    - Be stateless — given identical input, produce identical output (deterministic)
    - Not modify, cache, or persist the provider's internal data
    """
    
    @abstractmethod
    def convert(self, provider_chunk_data: Any) -> List[Chunk]:
        """
        Convert provider-specific chunk data into canonical Chunk entities.
        
        Args:
            provider_chunk_data: Provider-specific chunk data (e.g., Knowhere KnowledgeChunk, 
                                parser segment, embedding chunk)
        
        Returns:
            List[Chunk]: One or more canonical Chunk entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical Chunk entities
        """
        pass