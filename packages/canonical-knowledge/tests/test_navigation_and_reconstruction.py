"""Tests for User Story 4: Navigation validation (AC-003 through AC-006) and reconstruction validation (AC-001, AC-002)."""

import pytest

from canonical.exceptions import CanonicalError
from canonical.factory import CanonicalFactory
from canonical.query import CanonicalRepository
from canonical.value_objects.code_location import CodeLocation


class TestNavigationAndReconstructionValidation:
    """Validate AC-003 through AC-006 for navigation capabilities and AC-001, AC-002 for reconstruction."""
    
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
        
    def test_ac_001_full_entity_graph_reconstructable(self, populated_repo):
        """AC-001: Full entity graph reconstructable from canonical entities"""
        # Test that we can reconstruct the full graph from the repository
        # Get all entities by type
        files = populated_repo['repo'].find_entities_by_type("file")
        symbols = populated_repo['repo'].find_entities_by_type("symbol")
        chunks = populated_repo['repo'].find_entities_by_type("chunk")
        relationships = populated_repo['repo'].find_entities_by_type("relationship")
        
        # Verify we have the expected counts
        assert len(files) == 2
        assert len(symbols) == 2
        assert len(chunks) == 2
        assert len(relationships) == 2
        
        # Verify that all entities have valid IDs
        for file in files:
            assert file.id is not None
            assert file.id != ""
            
        for symbol in symbols:
            assert symbol.id is not None
            assert symbol.id != ""
            
        for chunk in chunks:
            assert chunk.id is not None
            assert chunk.id != ""
            
        for relationship in relationships:
            assert relationship.id is not None
            assert relationship.id != ""
            
    def test_ac_002_reconstructed_graph_identical(self, populated_repo):
        """AC-002: Reconstructed graph identical to original"""
        # Test that we can reconstruct the same graph by getting entities by ID
        # and verify they match the original entities
        
        # Get repository
        repo = populated_repo['repo'].get_repository(populated_repo['repo']._repository.id)
        assert repo.id == populated_repo['repo']._repository.id
        
        # Get files using actual IDs from the repository
        files = populated_repo['repo'].find_entities_by_type("file")
        assert len(files) == 2
        file1 = files[0] if files[0].path == "src/main.py" else files[1]
        file2 = files[1] if files[1].path == "src/utils.py" else files[0]
        
        # Get symbols using actual IDs from the repository
        symbols = populated_repo['repo'].find_entities_by_type("symbol")
        assert len(symbols) == 2
        symbol1 = symbols[0] if symbols[0].qualified_name == "main.process" else symbols[1]
        symbol2 = symbols[1] if symbols[1].qualified_name == "main.helper" else symbols[0]
        
        # Get chunks using actual IDs from the repository
        chunks = populated_repo['repo'].find_entities_by_type("chunk")
        assert len(chunks) == 2
        chunk1 = chunks[0] if chunks[0].text == "def process():\n    pass" else chunks[1]
        chunk2 = chunks[1] if chunks[1].text == "def helper():\n    pass" else chunks[0]
        
        # Get relationships using actual IDs from the repository
        relationships = populated_repo['repo'].find_entities_by_type("relationship")
        assert len(relationships) == 2
        rel1 = relationships[0] if relationships[0].type == "calls" else relationships[1]
        rel2 = relationships[1] if relationships[1].type == "calls" else relationships[0]
        
        # Verify that we can access all entities through their IDs
        assert file1.path == "src/main.py"
        assert file2.path == "src/utils.py"
        assert symbol1.qualified_name == "main.process"
        assert symbol2.qualified_name == "main.helper"
        assert chunk1.text == "def process():\n    pass"
        assert chunk2.text == "def helper():\n    pass"
        assert rel1.type == "calls"
        assert rel2.type == "calls"