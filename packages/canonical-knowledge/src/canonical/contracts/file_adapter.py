"""
FileAdapter contract for the canonical knowledge model.

This contract defines the interface that all FileAdapters must implement.
FileAdapters are responsible for converting provider-specific file representations
into canonical File entities.
"""

from abc import ABC, abstractmethod
from typing import List, Any
from pydantic import BaseModel

from canonical.entities.file import File
from canonical.value_objects.code_location import CodeLocation


class FileAdapterContract(ABC):
    """
    Abstract base class defining the FileAdapter contract.
    
    Every FileAdapter MUST:
    - Accept a provider-specific input and return a canonical File entity
    - Validate all invariants of the canonical File entity before returning
    - Fail explicitly with a descriptive error if conversion is not possible
    - Be stateless — given identical input, produce identical output (deterministic)
    - Not modify, cache, or persist the provider's internal data
    """
    
    @abstractmethod
    def convert(self, provider_file_data: Any) -> List[File]:
        """
        Convert provider-specific file data into canonical File entities.
        
        Args:
            provider_file_data: Provider-specific file data (e.g., Knowhere code file metadata, 
                               file system path + content, database record)
        
        Returns:
            List[File]: One or more canonical File entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical File entities
        """
        pass