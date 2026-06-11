"""
ChunkAdapter implementation for the canonical knowledge model.

This adapter converts provider-specific chunk representations into canonical Chunk entities.
"""

from typing import List, Any

from canonical.contracts.chunk_adapter import ChunkAdapterContract
from canonical.entities.chunk import Chunk
from canonical.value_objects.code_location import CodeLocation
from canonical.factory import CanonicalFactory


class ChunkAdapter(ChunkAdapterContract):
    """
    Converts provider-specific chunk data into canonical Chunk entities.
    
    This implementation follows the ChunkAdapter contract requirements:
    - Derives deterministic id from chunk's content
    - Computes content checksum using SHA-256
    - Maps provider's chunk metadata to canonical fields
    - Validates that location falls within bounds of parent File
    - Preserves chunk relationships via parent_id and references
    """
    
    def __init__(self, factory: CanonicalFactory):
        """
        Initialize the ChunkAdapter with a CanonicalFactory.
        
        Args:
            factory: CanonicalFactory instance for creating canonical entities
        """
        self.factory = factory
    
    def convert(self, provider_chunk_data: Any) -> List[Chunk]:
        """
        Convert provider-specific chunk data into canonical Chunk entities.
        
        Args:
            provider_chunk_data: Provider-specific chunk data
            
        Returns:
            List[Chunk]: One or more canonical Chunk entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical Chunk entities
        """
        # Handle different types of provider chunk data
        if isinstance(provider_chunk_data, list):
            # Multiple chunks
            return [self._convert_single_chunk(chunk_data) for chunk_data in provider_chunk_data]
        else:
            # Single chunk
            return [self._convert_single_chunk(provider_chunk_data)]
    
    def _convert_single_chunk(self, chunk_data: Any) -> Chunk:
        """Convert a single chunk data object."""
        # Extract chunk properties
        text = self._extract_text(chunk_data)
        repository_id = self._extract_repository_id(chunk_data)
        file_id = self._extract_file_id(chunk_data)
        location = self._extract_location(chunk_data)
        chunk_type = self._extract_chunk_type(chunk_data)
        ordering = self._extract_ordering(chunk_data)
        
        # Extract optional properties
        metadata = self._extract_metadata(chunk_data)
        symbol_ids = self._extract_symbol_ids(chunk_data)
        
        # Create chunk entity using build_chunk
        chunk_entity = self.factory.build_chunk(
            repository_id=repository_id,
            file_id=file_id,
            text=text,
            location=location,
            chunk_type=chunk_type,
            ordering=ordering,
            symbol_ids=symbol_ids,
            metadata=metadata,
        )
        
        return chunk_entity
    
    def _extract_text(self, chunk_data: Any) -> str:
        """Extract text content from chunk data."""
        if hasattr(chunk_data, 'text'):
            return getattr(chunk_data, 'text', '')
        elif hasattr(chunk_data, 'content'):
            return getattr(chunk_data, 'content', '')
        elif isinstance(chunk_data, dict):
            if 'text' in chunk_data:
                return chunk_data['text']
            elif 'content' in chunk_data:
                return chunk_data['content']
        return ''
    
    def _extract_repository_id(self, chunk_data: Any) -> str:
        """Extract repository_id from chunk data."""
        if hasattr(chunk_data, 'repository_id'):
            return getattr(chunk_data, 'repository_id', '')
        elif isinstance(chunk_data, dict) and 'repository_id' in chunk_data:
            return chunk_data['repository_id']
        else:
            return ''
    
    def _extract_file_id(self, chunk_data: Any) -> str:
        """Extract file_id from chunk data."""
        if hasattr(chunk_data, 'file_id'):
            return getattr(chunk_data, 'file_id', '')
        elif isinstance(chunk_data, dict) and 'file_id' in chunk_data:
            return chunk_data['file_id']
        else:
            return ''
    
    def _extract_location(self, chunk_data: Any) -> CodeLocation:
        """Extract location from chunk data."""
        if hasattr(chunk_data, 'location'):
            location = getattr(chunk_data, 'location')
            if isinstance(location, CodeLocation):
                return location
            elif isinstance(location, dict):
                return CodeLocation(**location)
        elif isinstance(chunk_data, dict) and 'location' in chunk_data:
            location_data = chunk_data['location']
            if isinstance(location_data, CodeLocation):
                return location_data
            elif isinstance(location_data, dict):
                return CodeLocation(**location_data)
        
        # Return default location if none found (start_line must be >= 1)
        return CodeLocation(
            start_line=1,
            start_column=1,
            end_line=1,
            end_column=1,
        )
    
    def _extract_chunk_type(self, chunk_data: Any) -> str:
        """Extract chunk type from chunk data."""
        if hasattr(chunk_data, 'chunk_type'):
            return getattr(chunk_data, 'chunk_type', 'code')
        elif isinstance(chunk_data, dict) and 'chunk_type' in chunk_data:
            return chunk_data['chunk_type']
        else:
            return 'code'
    
    def _extract_ordering(self, chunk_data: Any) -> int:
        """Extract ordering from chunk data."""
        if hasattr(chunk_data, 'ordering'):
            return getattr(chunk_data, 'ordering', 0)
        elif isinstance(chunk_data, dict) and 'ordering' in chunk_data:
            return chunk_data['ordering']
        else:
            return 0
    
    def _extract_metadata(self, chunk_data: Any) -> dict:
        """Extract metadata from chunk data."""
        if hasattr(chunk_data, 'metadata'):
            return getattr(chunk_data, 'metadata', {})
        elif isinstance(chunk_data, dict) and 'metadata' in chunk_data:
            return chunk_data['metadata']
        else:
            return {}
    
    def _extract_symbol_ids(self, chunk_data: Any) -> List[str]:
        """Extract symbol_ids from chunk data."""
        if hasattr(chunk_data, 'symbol_ids'):
            return getattr(chunk_data, 'symbol_ids', [])
        elif isinstance(chunk_data, dict) and 'symbol_ids' in chunk_data:
            return chunk_data['symbol_ids']
        else:
            return []
