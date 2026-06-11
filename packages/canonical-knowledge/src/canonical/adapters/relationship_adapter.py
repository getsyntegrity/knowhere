"""
RelationshipAdapter implementation for the canonical knowledge model.

This adapter converts provider-specific relationship representations into canonical Relationship entities.
"""

from typing import List, Any

from canonical.contracts.relationship_adapter import RelationshipAdapterContract
from canonical.entities.relationship import Relationship
from canonical.factory import CanonicalFactory


class RelationshipAdapter(RelationshipAdapterContract):
    """
    Converts provider-specific relationship data into canonical Relationship entities.
    
    This implementation follows the RelationshipAdapter contract requirements:
    - Derives deterministic id from source_id, target_id, and relationship_type
    - Maps provider's relationship metadata to canonical fields
    - Validates that source and target are valid canonical entity IDs
    - Preserves relationship semantics via type and properties
    """
    
    def __init__(self, factory: CanonicalFactory):
        """
        Initialize the RelationshipAdapter with a CanonicalFactory.
        
        Args:
            factory: CanonicalFactory instance for creating canonical entities
        """
        self.factory = factory
    
    def convert(self, provider_relationship_data: Any) -> List[Relationship]:
        """
        Convert provider-specific relationship data into canonical Relationship entities.
        
        Args:
            provider_relationship_data: Provider-specific relationship data
            
        Returns:
            List[Relationship]: One or more canonical Relationship entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical Relationship entities
        """
        # Handle different types of provider relationship data
        if isinstance(provider_relationship_data, list):
            # Multiple relationships
            return [self._convert_single_relationship(rel_data) for rel_data in provider_relationship_data]
        else:
            # Single relationship
            return [self._convert_single_relationship(provider_relationship_data)]
    
    def _convert_single_relationship(self, relationship_data: Any) -> Relationship:
        """Convert a single relationship data object."""
        # Extract relationship properties
        source_id = self._extract_source_id(relationship_data)
        target_id = self._extract_target_id(relationship_data)
        rel_type = self._extract_type(relationship_data)
        repository_id = self._extract_repository_id(relationship_data)
        
        # Extract optional properties
        weight = self._extract_weight(relationship_data)
        attributes = self._extract_attributes(relationship_data)
        metadata = self._extract_metadata(relationship_data)
        
        # Create relationship entity using build_relationship
        relationship_entity = self.factory.build_relationship(
            repository_id=repository_id,
            source_id=source_id,
            target_id=target_id,
            type=rel_type,
            weight=weight,
            attributes=attributes,
            metadata=metadata,
        )
        
        return relationship_entity
    
    def _extract_source_id(self, relationship_data: Any) -> str:
        """Extract source_id from relationship data."""
        if hasattr(relationship_data, 'source_id'):
            return getattr(relationship_data, 'source_id', '')
        elif isinstance(relationship_data, dict) and 'source_id' in relationship_data:
            return relationship_data['source_id']
        else:
            return ''
    
    def _extract_target_id(self, relationship_data: Any) -> str:
        """Extract target_id from relationship data."""
        if hasattr(relationship_data, 'target_id'):
            return getattr(relationship_data, 'target_id', '')
        elif isinstance(relationship_data, dict) and 'target_id' in relationship_data:
            return relationship_data['target_id']
        else:
            return ''
    
    def _extract_type(self, relationship_data: Any) -> str:
        """Extract relationship type from relationship data."""
        if hasattr(relationship_data, 'type'):
            return getattr(relationship_data, 'type', 'unknown')
        elif isinstance(relationship_data, dict) and 'type' in relationship_data:
            return relationship_data['type']
        else:
            return 'unknown'
    
    def _extract_repository_id(self, relationship_data: Any) -> str:
        """Extract repository_id from relationship data."""
        if hasattr(relationship_data, 'repository_id'):
            return getattr(relationship_data, 'repository_id', '')
        elif isinstance(relationship_data, dict) and 'repository_id' in relationship_data:
            return relationship_data['repository_id']
        else:
            return ''
    
    def _extract_weight(self, relationship_data: Any) -> float | None:
        """Extract weight from relationship data."""
        if hasattr(relationship_data, 'weight'):
            return getattr(relationship_data, 'weight', None)
        elif isinstance(relationship_data, dict) and 'weight' in relationship_data:
            return relationship_data['weight']
        else:
            return None
    
    def _extract_attributes(self, relationship_data: Any) -> dict:
        """Extract attributes from relationship data."""
        if hasattr(relationship_data, 'attributes'):
            return getattr(relationship_data, 'attributes', {})
        elif isinstance(relationship_data, dict) and 'attributes' in relationship_data:
            return relationship_data['attributes']
        else:
            return {}
    
    def _extract_metadata(self, relationship_data: Any) -> dict:
        """Extract metadata from relationship data."""
        if hasattr(relationship_data, 'metadata'):
            return getattr(relationship_data, 'metadata', {})
        elif isinstance(relationship_data, dict) and 'metadata' in relationship_data:
            return relationship_data['metadata']
        else:
            return {}
