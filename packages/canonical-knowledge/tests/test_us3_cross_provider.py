"""Tests for User Story 3 — Cross-Provider Consistency (AC-010, AC-011, AC-012, AC-013)."""

import hashlib

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.relationship import Relationship
from canonical.entities.symbol import Symbol
from canonical.factory import CanonicalFactory
from canonical.value_objects.code_location import CodeLocation


class TestCrossProviderConsistency:
    """T031: Validate AC-010, AC-011 (provider equivalence)."""
    
    def test_same_text_same_semantic_hash_across_providers(self):
        """AC-010: Two providers produce identical semantic_hash for identical text.
        
        Independent Test: Index the same file with two adapters and compare.
        """
        factory_a = CanonicalFactory()
        factory_b = CanonicalFactory()
        
        repo_a = factory_a.build_repository(
            name="test", source_uri="https://github.com/test", source="provider-a",
        )
        repo_b = factory_b.build_repository(
            name="test", source_uri="https://github.com/test", source="provider-b",
        )
        
        file_a = factory_a.build_file(
            repository_id=repo_a.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        file_b = factory_b.build_file(
            repository_id=repo_b.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        
        # Same text at different locations (to test semantic_hash is text-only)
        text = "def hello():\n    pass"
        chunk_a = factory_a.build_chunk(
            repository_id=repo_a.id, file_id=file_a.id,
            text=text,
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        chunk_b = factory_b.build_chunk(
            repository_id=repo_b.id, file_id=file_b.id,
            text=text,
            location=CodeLocation(start_line=5, start_column=1, end_line=6, end_column=9),
            chunk_type="code", ordering=0,
        )
        
        # Same text → same semantic_hash regardless of location or provider
        assert chunk_a.semantic_hash == chunk_b.semantic_hash
        
        # Different locations → different chunk_id
        assert chunk_a.id != chunk_b.id
    
    def test_equivalent_to_relationship(self):
        """AC-011: equivalent_to relationship links corresponding entities from different providers.
        
        Independent Test: Index the same file with two adapters and link equivalents.
        """
        factory = CanonicalFactory()
        
        repo_a = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="provider-a",
        )
        repo_b = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="provider-b",
        )
        
        # Same file content in both repositories
        file_a = factory.build_file(
            repository_id=repo_a.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        file_b = factory.build_file(
            repository_id=repo_b.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        
        # Same symbol in both
        symbol_a = factory.build_symbol(
            repository_id=repo_a.id, file_id=file_a.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        symbol_b = factory.build_symbol(
            repository_id=repo_b.id, file_id=file_b.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # Same text content → same semantic_hash
        text = "def hello():\n    pass"
        chunk_a = factory.build_chunk(
            repository_id=repo_a.id, file_id=file_a.id,
            text=text,
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        chunk_b = factory.build_chunk(
            repository_id=repo_b.id, file_id=file_b.id,
            text=text,
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        
        # Create equivalent_to relationships
        rel_a = factory.build_relationship(
            repository_id=repo_a.id,
            source_id=symbol_a.id, target_id=symbol_b.id, type="equivalent_to",
        )
        rel_b = factory.build_relationship(
            repository_id=repo_a.id,
            source_id=chunk_a.id, target_id=chunk_b.id, type="equivalent_to",
        )
        
        # Verify relationships exist
        assert rel_a.type == "equivalent_to"
        assert rel_b.type == "equivalent_to"
        
        # Verify semantic hashes match
        assert chunk_a.semantic_hash == chunk_b.semantic_hash
        
        # Verify different repositories have different IDs
        assert repo_a.id != repo_b.id
        
        # Verify same file path but different repo produces different file ID
        assert file_a.id != file_b.id


class TestDeterminism:
    """T032: Validate AC-012, AC-013 (determinism)."""
    
    def test_same_input_same_ids_across_runs(self):
        """AC-012: Indexing the same source twice produces identical canonical entities.
        
        Independent Test: Run factory twice with same input.
        """
        factory = CanonicalFactory()
        
        # First run
        repo1 = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        file1 = factory.build_file(
            repository_id=repo1.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        symbol1 = factory.build_symbol(
            repository_id=repo1.id, file_id=file1.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # Second run (same input)
        repo2 = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        file2 = factory.build_file(
            repository_id=repo2.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        symbol2 = factory.build_symbol(
            repository_id=repo2.id, file_id=file2.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # All IDs must match
        assert repo1.id == repo2.id
        assert file1.id == file2.id
        assert symbol1.id == symbol2.id
        
        # All deterministic fields must match (excluding created_at which is timestamp-based)
        assert repo1.name == repo2.name
        assert repo1.source_uri == repo2.source_uri
        assert repo1.source == repo2.source
        assert file1.path == file2.path
        assert file1.checksum == file2.checksum
        assert file1.size_bytes == file2.size_bytes
        assert symbol1.name == symbol2.name
        assert symbol1.qualified_name == symbol2.qualified_name
        assert symbol1.kind == symbol2.kind
    
    def test_reordered_creation_same_entities(self):
        """AC-013: Re-ordering entity creation does not change results.
        
        Independent Test: Create entities in different order, compare results.
        """
        factory = CanonicalFactory()
        
        # Order A: repo → file → symbol → chunk
        repo_a = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        file_a = factory.build_file(
            repository_id=repo_a.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        symbol_a = factory.build_symbol(
            repository_id=repo_a.id, file_id=file_a.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        chunk_a = factory.build_chunk(
            repository_id=repo_a.id, file_id=file_a.id,
            text="def hello():\n    pass",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        
        # Order B: repo → file → chunk → symbol (different order)
        repo_b = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        file_b = factory.build_file(
            repository_id=repo_b.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        chunk_b = factory.build_chunk(
            repository_id=repo_b.id, file_id=file_b.id,
            text="def hello():\n    pass",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        symbol_b = factory.build_symbol(
            repository_id=repo_b.id, file_id=file_b.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # All IDs must match regardless of creation order
        assert repo_a.id == repo_b.id
        assert file_a.id == file_b.id
        assert symbol_a.id == symbol_b.id
        assert chunk_a.id == chunk_b.id
        
        # All deterministic fields must match
        assert repo_a.name == repo_b.name
        assert repo_a.source_uri == repo_b.source_uri
        assert repo_a.source == repo_b.source
        assert file_a.path == file_b.path
        assert file_a.checksum == file_b.checksum
        assert file_a.size_bytes == file_b.size_bytes
        assert symbol_a.name == symbol_b.name
        assert symbol_a.qualified_name == symbol_b.qualified_name
        assert symbol_a.kind == symbol_b.kind
        assert chunk_a.text == chunk_b.text
        assert chunk_a.chunk_type == chunk_b.chunk_type
        assert chunk_a.ordering == chunk_b.ordering
    
    def test_parallel_creation_same_entities(self):
        """AC-013: Parallel entity creation does not change results.
        
        Simulate parallel creation by creating entities independently.
        """
        factory = CanonicalFactory()
        
        # Independent creation (simulating parallel)
        repo1 = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        repo2 = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        
        file1 = factory.build_file(
            repository_id=repo1.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        file2 = factory.build_file(
            repository_id=repo2.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        
        # IDs must match despite independent creation
        assert repo1.id == repo2.id
        assert file1.id == file2.id
    
    def test_canonical_identifiers_same_file_same_location(self):
        """AC-010: Same file at same location produces identical canonical identifiers.
        
        This is the core cross-provider equivalence test.
        """
        factory_a = CanonicalFactory()
        factory_b = CanonicalFactory()
        
        # Same source, same provider label
        repo_a = factory_a.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        repo_b = factory_b.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        
        # Same file
        file_a = factory_a.build_file(
            repository_id=repo_a.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        file_b = factory_b.build_file(
            repository_id=repo_b.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        
        # Same file → same ID
        assert file_a.id == file_b.id
        
        # Same symbol at same location
        symbol_a = factory_a.build_symbol(
            repository_id=repo_a.id, file_id=file_a.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        symbol_b = factory_b.build_symbol(
            repository_id=repo_b.id, file_id=file_b.id,
            name="hello", qualified_name="main.hello", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # Same symbol → same ID
        assert symbol_a.id == symbol_b.id
    
    def test_semantic_hash_deduplication(self):
        """AC-010: semantic_hash enables cross-provider deduplication.
        
        Two chunks with identical text but different locations have same semantic_hash.
        """
        factory = CanonicalFactory()
        repo = factory.build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        file = factory.build_file(
            repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100,
        )
        
        text = "def common_utility():\n    return 42"
        
        # Chunk at location 1
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text=text,
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=15),
            chunk_type="code", ordering=0,
        )
        
        # Chunk at location 2 (same text, different location)
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text=text,
            location=CodeLocation(start_line=10, start_column=1, end_line=11, end_column=15),
            chunk_type="code", ordering=1,
        )
        
        # Same text → same semantic_hash
        assert chunk1.semantic_hash == chunk2.semantic_hash
        
        # Different locations → different chunk_id
        assert chunk1.id != chunk2.id
        
        # Verify semantic_hash is computed from text only
        expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert chunk1.semantic_hash == expected_hash
        assert chunk2.semantic_hash == expected_hash
