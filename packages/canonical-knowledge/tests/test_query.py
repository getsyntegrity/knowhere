"""Tests for CanonicalRepository query interface."""

import pytest

from canonical.exceptions import CanonicalError
from canonical.factory import CanonicalFactory
from canonical.query import CanonicalRepository
from canonical.value_objects.code_location import CodeLocation


class TestCanonicalRepository:
    """T024: CanonicalRepository tests."""
    
    @pytest.fixture
    def populated_repo(self):
        """A repository with multiple entities."""
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
        
        rel = factory.build_relationship(
            repository_id=repo.id, source_id=symbol1.id, target_id=symbol2.id, type="calls",
        )
        
        ref = factory.build_reference(
            repository_id=repo.id, source_id=file1.id, target_id=symbol1.id,
            source_file_id=file1.id, target_file_id=file1.id,
            location=CodeLocation(start_line=10, start_column=1, end_line=10, end_column=10),
            role="call",
        )
        
        return repo, [file1, file2], [symbol1, symbol2], [chunk1, chunk2], [rel], [ref]
    
    def test_get_file_by_id(self, populated_repo):
        """Retrieve file by ID."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        file = query.get_file(files[0].id)
        assert file.path == "src/main.py"
    
    def test_get_symbol_by_id(self, populated_repo):
        """Retrieve symbol by ID."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        symbol = query.get_symbol(symbols[0].id)
        assert symbol.qualified_name == "main.process"
    
    def test_find_symbols_by_file(self, populated_repo):
        """Find all symbols in a file."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        file_symbols = query.find_symbols(files[0].id)
        assert len(file_symbols) == 2
        assert all(s.file_id == files[0].id for s in file_symbols)
    
    def test_find_chunks_by_file_in_ordering(self, populated_repo):
        """Find chunks in file ordered by ordering."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        file_chunks = query.find_chunks(files[0].id)
        assert len(file_chunks) == 2
        assert file_chunks[0].ordering == 0
        assert file_chunks[1].ordering == 1
    
    def test_find_relationships_by_source(self, populated_repo):
        """Find relationships by source."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        rels_from_symbol = query.find_relationships(symbols[0].id)
        assert len(rels_from_symbol) == 1
        assert rels_from_symbol[0].type == "calls"
    
    def test_find_relationships_by_target(self, populated_repo):
        """Find relationships by target."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        rels_to_symbol = query.find_relationships_by_target(symbols[1].id)
        assert len(rels_to_symbol) == 1
    
    def test_get_file_by_path(self, populated_repo):
        """Retrieve file by path."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        file = query.get_file_by_path(repo.id, "src/main.py")
        assert file.path == "src/main.py"
    
    def test_get_symbol_by_name(self, populated_repo):
        """Retrieve symbol by qualified name."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        symbol = query.get_symbol_by_name(repo.id, "main.process")
        assert symbol.name == "process"
    
    def test_entity_not_found(self, populated_repo):
        """Entity not found raises error."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        with pytest.raises(CanonicalError):
            query.get_file("non-existent-id")
    
    def test_find_entities_by_type(self, populated_repo):
        """Find all entities of a given type."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        query = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        assert len(query.find_entities_by_type("file")) == 2
        assert len(query.find_entities_by_type("symbol")) == 2
        assert len(query.find_entities_by_type("chunk")) == 2
        assert len(query.find_entities_by_type("relationship")) == 1
        assert len(query.find_entities_by_type("reference")) == 1
    
    def test_stateless_construction(self, populated_repo):
        """CanonicalRepository is stateless with respect to external storage."""
        repo, files, symbols, chunks, rels, refs = populated_repo
        
        # Create two instances with same data
        query1 = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        query2 = CanonicalRepository(repo, files, symbols, chunks, rels, refs)
        
        # Both should return same results
        assert query1.get_file(files[0].id) == query2.get_file(files[0].id)
    
    def test_no_persistence_dependencies(self):
        """CanonicalRepository has no persistence dependencies."""
        repo = CanonicalFactory().build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        query = CanonicalRepository(repo)
        
        # Should work without any database/storage setup
        assert query.get_repository(repo.id) == repo
