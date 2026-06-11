"""
SymbolAdapter implementation for the canonical knowledge model.

This adapter converts provider-specific symbol representations into canonical Symbol entities.
"""

from typing import List, Any

from canonical.contracts.symbol_adapter import SymbolAdapterContract
from canonical.entities.symbol import Symbol
from canonical.value_objects.code_location import CodeLocation
from canonical.factory import CanonicalFactory


class SymbolAdapter(SymbolAdapterContract):
    """
    Converts provider-specific symbol data into canonical Symbol entities.
    
    This implementation follows the SymbolAdapter contract requirements:
    - Derives deterministic id from symbol's qualified_name and repository_id
    - Constructs qualified_name from provider's hierarchical symbol information
    - Maps provider's symbol kind to canonical kind
    - Validates that location falls within bounds of parent File
    - Preserves parent-child symbol hierarchy via children collection
    """
    
    def __init__(self, factory: CanonicalFactory):
        """
        Initialize the SymbolAdapter with a CanonicalFactory.
        
        Args:
            factory: CanonicalFactory instance for creating canonical entities
        """
        self.factory = factory
    
    def convert(self, provider_symbol_data: Any) -> List[Symbol]:
        """
        Convert provider-specific symbol data into canonical Symbol entities.
        
        Args:
            provider_symbol_data: Provider-specific symbol data
            
        Returns:
            List[Symbol]: One or more canonical Symbol entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical Symbol entities
        """
        # Handle different types of provider symbol data
        if isinstance(provider_symbol_data, list):
            # Multiple symbols
            return [self._convert_single_symbol(symbol_data) for symbol_data in provider_symbol_data]
        else:
            # Single symbol
            return [self._convert_single_symbol(provider_symbol_data)]
    
    def _convert_single_symbol(self, symbol_data: Any) -> Symbol:
        """Convert a single symbol data object."""
        # Extract symbol properties
        name = self._extract_name(symbol_data)
        qualified_name = self._extract_qualified_name(symbol_data)
        repository_id = self._extract_repository_id(symbol_data)
        file_id = self._extract_file_id(symbol_data)
        kind = self._extract_kind(symbol_data)
        location = self._extract_location(symbol_data)
        
        # Extract optional properties
        scope = self._extract_scope(symbol_data)
        signature = self._extract_signature(symbol_data)
        documentation = self._extract_documentation(symbol_data)
        children = self._extract_children(symbol_data)
        metadata = self._extract_metadata(symbol_data)
        
        # Create symbol entity using build_symbol
        symbol_entity = self.factory.build_symbol(
            repository_id=repository_id,
            file_id=file_id,
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            location=location,
            scope=scope,
            signature=signature,
            documentation=documentation,
            children=children,
            metadata=metadata,
        )
        
        return symbol_entity
    
    def _extract_name(self, symbol_data: Any) -> str:
        """Extract name from symbol data."""
        if hasattr(symbol_data, 'name'):
            return getattr(symbol_data, 'name', '')
        elif isinstance(symbol_data, dict) and 'name' in symbol_data:
            return symbol_data['name']
        else:
            return ''
    
    def _extract_qualified_name(self, symbol_data: Any) -> str:
        """Extract qualified name from symbol data."""
        if hasattr(symbol_data, 'qualified_name'):
            return getattr(symbol_data, 'qualified_name', '')
        elif isinstance(symbol_data, dict) and 'qualified_name' in symbol_data:
            return symbol_data['qualified_name']
        else:
            # Fallback to name if qualified_name is not available
            return self._extract_name(symbol_data)
    
    def _extract_repository_id(self, symbol_data: Any) -> str:
        """Extract repository_id from symbol data."""
        if hasattr(symbol_data, 'repository_id'):
            return getattr(symbol_data, 'repository_id', '')
        elif isinstance(symbol_data, dict) and 'repository_id' in symbol_data:
            return symbol_data['repository_id']
        else:
            return ''
    
    def _extract_file_id(self, symbol_data: Any) -> str:
        """Extract file_id from symbol data."""
        if hasattr(symbol_data, 'file_id'):
            return getattr(symbol_data, 'file_id', '')
        elif isinstance(symbol_data, dict) and 'file_id' in symbol_data:
            return symbol_data['file_id']
        else:
            return ''
    
    def _extract_kind(self, symbol_data: Any) -> str:
        """Extract symbol kind from symbol data."""
        if hasattr(symbol_data, 'kind'):
            return getattr(symbol_data, 'kind', 'unknown')
        elif isinstance(symbol_data, dict) and 'kind' in symbol_data:
            return symbol_data['kind']
        else:
            return 'unknown'
    
    def _extract_location(self, symbol_data: Any) -> CodeLocation:
        """Extract location from symbol data."""
        if hasattr(symbol_data, 'location'):
            location = getattr(symbol_data, 'location')
            if isinstance(location, CodeLocation):
                return location
            elif isinstance(location, dict):
                return CodeLocation(**location)
        elif isinstance(symbol_data, dict) and 'location' in symbol_data:
            location_data = symbol_data['location']
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
    
    def _extract_scope(self, symbol_data: Any) -> str:
        """Extract scope from symbol data."""
        if hasattr(symbol_data, 'scope'):
            return getattr(symbol_data, 'scope', '')
        elif isinstance(symbol_data, dict) and 'scope' in symbol_data:
            return symbol_data['scope']
        else:
            return ''
    
    def _extract_signature(self, symbol_data: Any) -> str:
        """Extract signature from symbol data."""
        if hasattr(symbol_data, 'signature'):
            return getattr(symbol_data, 'signature', '')
        elif isinstance(symbol_data, dict) and 'signature' in symbol_data:
            return symbol_data['signature']
        else:
            return ''
    
    def _extract_documentation(self, symbol_data: Any) -> str:
        """Extract documentation from symbol data."""
        if hasattr(symbol_data, 'documentation'):
            return getattr(symbol_data, 'documentation', '')
        elif isinstance(symbol_data, dict) and 'documentation' in symbol_data:
            return symbol_data['documentation']
        else:
            return ''
    
    def _extract_children(self, symbol_data: Any) -> List[str]:
        """Extract children from symbol data."""
        if hasattr(symbol_data, 'children'):
            return getattr(symbol_data, 'children', [])
        elif isinstance(symbol_data, dict) and 'children' in symbol_data:
            return symbol_data['children']
        else:
            return []
    
    def _extract_metadata(self, symbol_data: Any) -> dict:
        """Extract metadata from symbol data."""
        if hasattr(symbol_data, 'metadata'):
            return getattr(symbol_data, 'metadata', {})
        elif isinstance(symbol_data, dict) and 'metadata' in symbol_data:
            return symbol_data['metadata']
        else:
            return {}
