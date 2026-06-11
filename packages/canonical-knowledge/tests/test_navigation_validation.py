"""Tests for User Story 4: Navigation validation (AC-003 through AC-006)."""

import pytest

from canonical.exceptions import CanonicalError
from canonical.factory import CanonicalFactory
from canonical.query import CanonicalRepository
from canonical.value_objects.code_location import CodeLocation


class TestNavigationValidation:
    """Validate AC-003 through AC-006 for navigation capabilities."""
    
    @pytest.fixture
    def populated_repo(self):
        """A repository with multiple entities for navigation testing."""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file1 = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        file2 = factory.build_file(repository_id=repo.id, path="src/utils.py", checksum="def", size_bytes=50)
        
        symbol1 = factory.build_symbol(
            repository_id=repo.id, file_id=file1.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        symbol2 = factory.build_symbol(
            repository_id=repo.id, file_id=file1.id,
            name="helper", qualified_name="main.helper", kind="function",
            location=CodeLocation(start_line=5, start_column=1, end_line=5, end_column=10),
        )
        
        # Create chunks for file1
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file1.id,
            text="def process():\n    pass",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file1.id,
            text="def helper():\n    pass",
            location=CodeLocation(start_line=5, start_column=1, end_line=6, end_column=9),
            chunk_type="code", ordering=1,
        )
        
        # Create relationships
        rel1 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol1.id, target_id=symbol2.id, type="calls",
        )
        rel2 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol2.id, target_id=symbol1.id, type="calls",
        )
        
        # Create a batch to test navigation
        return {
            'repo': CanonicalRepository(
                repository=repo,
                files=[file1, file2],
                symbols=[symbol1, symbol2],
                chunks=[chunk1, chunk2],
                relationships=[rel1, rel2]
            ),
            'file1': file1,
            'file2': file2,
            'symbol1': symbol1,
            'symbol2': symbol2,
            'chunk1': chunk1,
            'chunk2': chunk2,
            'rel1': rel1,
            'rel2': rel2,
        }
    
    def test_ac_003_symbol_to_file_navigation(self, populated_repo):
        """AC-003: Symbol → File navigation"""
        # Use the symbol created in the fixture
        symbol = populated_repo['symbol1']
        
        # Navigate to the file using the symbol's file_id
        file = populated_repo['repo'].get_file(symbol.file_id)
        
        # Verify the navigation
        assert file.id == symbol.file_id
        assert file.path == "src/main.py"
        
    def test_ac_004_chunk_to_source_location_navigation(self, populated_repo):
        """AC-004: Chunk → source location navigation"""
        # Use the chunk created in the fixture
        chunk = populated_repo['chunk1']
        
        # Navigate to the file using the chunk's file_id
        file = populated_repo['repo'].get_file(chunk.file_id)
        
        # Verify the navigation
        assert file.id == chunk.file_id
        assert file.path == "src/main.py"
        
        # Verify the chunk's location
        assert chunk.location.start_line == 1
        assert chunk.location.end_line == 2
        
    def test_ac_005_file_to_symbols_enumeration(self, populated_repo):
        """AC-005: File → Symbols enumeration"""
        # Use the file created in the fixture
        file = populated_repo['file1']
        
        # Get all symbols for this file
        symbols = populated_repo['repo'].find_symbols(file_id=file.id)
        
        # Verify we get the right symbols
        assert len(symbols) == 2
        symbol_names = [s.qualified_name for s in symbols]
        assert "main.process" in symbol_names
        assert "main.helper" in symbol_names
        
    def test_ac_006_relationship_query_by_entity(self, populated_repo):
        """AC-006: Relationship query by entity"""
        # Use the symbol created in the fixture
        symbol = populated_repo['symbol1']
        
        # Query relationships where this symbol is the source
        relationships = populated_repo['repo'].find_relationships(source_id=symbol.id)
        
        # Verify we get the right relationships
        assert len(relationships) == 1
        assert relationships[0].type == "calls"
        assert relationships[0].target_id == populated_repo['symbol2'].id
        
        # Query relationships where this symbol is the target
        relationships_target = populated_repo['repo'].find_relationships_by_target(symbol.id)
        
        # Verify we get the right relationships
        assert len(relationships_target) == 1
        assert relationships_target[0].type == "calls"
        assert relationships_target[0].source_id == populated_repo['symbol2'].id