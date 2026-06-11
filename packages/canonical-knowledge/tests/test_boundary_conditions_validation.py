"""Tests for User Story 6: Boundary conditions validation (AC-017 through AC-024)."""

import pytest
import hashlib

from canonical.exceptions import CanonicalError
from canonical.factory import CanonicalFactory
from canonical.query import CanonicalRepository
from canonical.value_objects.code_location import CodeLocation


class TestBoundaryConditionsValidation:
    """Validate AC-017 through AC-024 for boundary conditions."""
    
    def test_ac_017_empty_repository(self):
        """AC-017: Empty repository handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="empty", source_uri="https://github.com/empty", source="knowhere")
        
        # Create empty repository
        empty_repo = CanonicalRepository(
            repository=repo,
            files=[],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        # Test that we can still access the repository
        retrieved_repo = empty_repo.get_repository(repo.id)
        assert retrieved_repo.id == repo.id
        
        # Test that queries return empty results
        files = empty_repo.find_entities_by_type("file")
        symbols = empty_repo.find_entities_by_type("symbol")
        chunks = empty_repo.find_entities_by_type("chunk")
        relationships = empty_repo.find_entities_by_type("relationship")
        
        assert len(files) == 0
        assert len(symbols) == 0
        assert len(chunks) == 0
        assert len(relationships) == 0
        
    def test_ac_018_single_file_repository(self):
        """AC-018: Single file repository handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="single", source_uri="https://github.com/single", source="knowhere")
        file1 = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        # Create repository with single file
        single_file_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        # Test that we can access the file
        retrieved_file = single_file_repo.get_file(file1.id)
        assert retrieved_file.id == file1.id
        assert retrieved_file.path == "src/main.py"
        
        # Test that queries return expected results
        files = single_file_repo.find_entities_by_type("file")
        symbols = single_file_repo.find_entities_by_type("symbol")
        chunks = single_file_repo.find_entities_by_type("chunk")
        relationships = single_file_repo.find_entities_by_type("relationship")
        
        assert len(files) == 1
        assert len(symbols) == 0
        assert len(chunks) == 0
        assert len(relationships) == 0
        
    def test_ac_019_large_files_handling(self):
        """AC-019: Large files handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="large", source_uri="https://github.com/large", source="knowhere")
        
        # Create a large file with lots of content
        large_content = "def large_function():\n" + "    # This is a large function\n" * 1000 + "\n    return True"
        large_checksum = hashlib.sha256(large_content.encode("utf-8")).hexdigest()
        
        file1 = factory.build_file(
            repository_id=repo.id, 
            path="src/large.py", 
            checksum=large_checksum, 
            size_bytes=len(large_content)
        )
        
        # Create repository with large file
        large_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        # Test that we can access the large file
        retrieved_file = large_repo.get_file(file1.id)
        assert retrieved_file.id == file1.id
        assert retrieved_file.path == "src/large.py"
        assert retrieved_file.size_bytes == len(large_content)
        
    def test_ac_020_unicode_handling(self):
        """AC-020: Unicode handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="unicode", source_uri="https://github.com/unicode", source="knowhere")
        
        # Create file with unicode content
        unicode_path = "src/unicode_测试.py"
        file1 = factory.build_file(
            repository_id=repo.id, 
            path=unicode_path, 
            checksum="abc", 
            size_bytes=100
        )
        
        # Create repository with unicode file
        unicode_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        # Test that we can access the unicode file
        retrieved_file = unicode_repo.get_file(file1.id)
        assert retrieved_file.id == file1.id
        assert retrieved_file.path == unicode_path
        
    def test_ac_021_circular_symbols_handling(self):
        """AC-021: Circular symbols handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="circular", source_uri="https://github.com/circular", source="knowhere")
        file1 = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        # Create circular relationship symbols
        symbol1 = factory.build_symbol(
            repository_id=repo.id, file_id=file1.id,
            name="func1", qualified_name="main.func1", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        symbol2 = factory.build_symbol(
            repository_id=repo.id, file_id=file1.id,
            name="func2", qualified_name="main.func2", kind="function",
            location=CodeLocation(start_line=5, start_column=1, end_line=5, end_column=10),
        )
        
        # Create circular relationships
        rel1 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol1.id, target_id=symbol2.id, type="calls",
        )
        rel2 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol2.id, target_id=symbol1.id, type="calls",
        )
        
        # Create repository with circular relationships
        circular_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[symbol1, symbol2],
            chunks=[],
            relationships=[rel1, rel2]
        )
        
        # Test that we can access all entities
        retrieved_symbol1 = circular_repo.get_symbol(symbol1.id)
        retrieved_symbol2 = circular_repo.get_symbol(symbol2.id)
        retrieved_rel1 = circular_repo.get_relationship(rel1.id)
        retrieved_rel2 = circular_repo.get_relationship(rel2.id)
        
        assert retrieved_symbol1.qualified_name == "main.func1"
        assert retrieved_symbol2.qualified_name == "main.func2"
        assert retrieved_rel1.type == "calls"
        assert retrieved_rel2.type == "calls"
        
    def test_ac_022_binary_files_handling(self):
        """AC-022: Binary files handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="binary", source_uri="https://github.com/binary", source="knowhere")
        
        # Create binary file (using a binary checksum)
        binary_checksum = "a1b2c3d4e5f67890123456789012345678901234567890123456789012345678"
        file1 = factory.build_file(
            repository_id=repo.id, 
            path="src/image.png", 
            checksum=binary_checksum, 
            size_bytes=1024
        )
        
        # Create repository with binary file
        binary_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        # Test that we can access the binary file
        retrieved_file = binary_repo.get_file(file1.id)
        assert retrieved_file.id == file1.id
        assert retrieved_file.path == "src/image.png"
        assert retrieved_file.checksum == binary_checksum
        
    def test_ac_023_missing_optional_fields(self):
        """AC-023: Missing optional fields handling"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="optional", source_uri="https://github.com/optional", source="knowhere")
        
        # Create file with minimal required fields
        file1 = factory.build_file(
            repository_id=repo.id, 
            path="src/minimal.py", 
            checksum="abc", 
            size_bytes=100
        )
        
        # Create repository with minimal file
        minimal_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[],
            relationships=[]
        )
        
        # Test that we can access the file with optional fields
        retrieved_file = minimal_repo.get_file(file1.id)
        assert retrieved_file.id == file1.id
        assert retrieved_file.path == "src/minimal.py"
        # Optional fields should be None or empty
        assert retrieved_file.language is None
        assert retrieved_file.metadata == {}
        
    def test_ac_024_semantic_hash_different_chunk_id(self):
        """AC-024: Same semantic_hash / different chunk_id"""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="hash", source_uri="https://github.com/hash", source="knowhere")
        file1 = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        # Create two chunks with same semantic hash but different content (different IDs)
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file1.id,
            text="def func():\n    return True",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
            semantic_hash="same_hash_12345678901234567890123456789012"  # Same hash
        )
        
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file1.id,
            text="def func():\n    return False",  # Different content
            location=CodeLocation(start_line=3, start_column=1, end_line=4, end_column=9),
            chunk_type="code", ordering=1,
            semantic_hash="same_hash_12345678901234567890123456789012"  # Same hash
        )
        
        # Create repository with chunks
        hash_repo = CanonicalRepository(
            repository=repo,
            files=[file1],
            symbols=[],
            chunks=[chunk1, chunk2],
            relationships=[]
        )
        
        # Test that we can access both chunks
        retrieved_chunk1 = hash_repo.get_chunk(chunk1.id)
        retrieved_chunk2 = hash_repo.get_chunk(chunk2.id)
        
        # Both should have the same semantic hash but different IDs and content
        assert retrieved_chunk1.semantic_hash == retrieved_chunk2.semantic_hash
        assert retrieved_chunk1.id != retrieved_chunk2.id
        assert retrieved_chunk1.text != retrieved_chunk2.text
        assert retrieved_chunk1.text == "def func():\n    return True"
        assert retrieved_chunk2.text == "def func():\n    return False"