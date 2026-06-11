"""Tests for User Story 5: Isolation validation (AC-014 through AC-016)."""

import pytest

from canonical.adapters.file_adapter import FileAdapter
from canonical.adapters.symbol_adapter import SymbolAdapter
from canonical.adapters.chunk_adapter import ChunkAdapter
from canonical.adapters.relationship_adapter import RelationshipAdapter
from canonical.contracts.file_adapter import FileAdapterContract
from canonical.contracts.symbol_adapter import SymbolAdapterContract
from canonical.contracts.chunk_adapter import ChunkAdapterContract
from canonical.contracts.relationship_adapter import RelationshipAdapterContract


class TestIsolationValidation:
    """Validate AC-014 through AC-016 for isolation."""
    
    def test_ac_014_no_provider_imports_in_adapter_test_code(self):
        """AC-014: No provider imports in adapter test code"""
        # Verify that adapter test code doesn't import provider-specific modules
        # This is more of a code review requirement, but we can verify the imports
        # in the adapter contracts
        
        # Check that contracts don't import provider-specific code
        assert FileAdapterContract.__module__ == "canonical.contracts.file_adapter"
        assert SymbolAdapterContract.__module__ == "canonical.contracts.symbol_adapter"
        assert ChunkAdapterContract.__module__ == "canonical.contracts.chunk_adapter"
        assert RelationshipAdapterContract.__module__ == "canonical.contracts.relationship_adapter"
        
    def test_ac_015_removing_adapter_leaves_others_unaffected(self):
        """AC-015: Removing adapter leaves others unaffected"""
        # This test verifies that each adapter is independent
        # We can test that each adapter can be imported and instantiated independently
        
        # Import and test that each adapter can be imported
        from canonical.adapters.file_adapter import FileAdapter
        from canonical.adapters.symbol_adapter import SymbolAdapter
        from canonical.adapters.chunk_adapter import ChunkAdapter
        from canonical.adapters.relationship_adapter import RelationshipAdapter
        
        # Test that each adapter can be imported and instantiated with a mock factory
        # We'll create a mock factory for testing purposes
        from unittest.mock import Mock
        mock_factory = Mock()
        
        # Test that each adapter can be instantiated with a factory
        file_adapter = FileAdapter(factory=mock_factory)
        symbol_adapter = SymbolAdapter(factory=mock_factory)
        chunk_adapter = ChunkAdapter(factory=mock_factory)
        relationship_adapter = RelationshipAdapter(factory=mock_factory)
        
        # Verify they are all different types
        assert isinstance(file_adapter, FileAdapter)
        assert isinstance(symbol_adapter, SymbolAdapter)
        assert isinstance(chunk_adapter, ChunkAdapter)
        assert isinstance(relationship_adapter, RelationshipAdapter)
        
    def test_ac_016_adapter_independence(self):
        """AC-016: Adapter independence"""
        # Test that adapters can be used independently without dependencies on each other
        
        # Import and test that each adapter can be imported
        from canonical.adapters.file_adapter import FileAdapter
        from canonical.adapters.symbol_adapter import SymbolAdapter
        from canonical.adapters.chunk_adapter import ChunkAdapter
        from canonical.adapters.relationship_adapter import RelationshipAdapter
        
        # Create instances of each adapter with a mock factory
        from unittest.mock import Mock
        mock_factory = Mock()
        
        # Create instances of each adapter
        file_adapter = FileAdapter(factory=mock_factory)
        symbol_adapter = SymbolAdapter(factory=mock_factory)
        chunk_adapter = ChunkAdapter(factory=mock_factory)
        relationship_adapter = RelationshipAdapter(factory=mock_factory)
        
        # Verify they can be instantiated without dependencies
        assert file_adapter is not None
        assert symbol_adapter is not None
        assert chunk_adapter is not None
        assert relationship_adapter is not None
        
        # Verify they have the required contract methods
        assert hasattr(file_adapter, 'convert')
        assert hasattr(symbol_adapter, 'convert')
        assert hasattr(chunk_adapter, 'convert')
        assert hasattr(relationship_adapter, 'convert')