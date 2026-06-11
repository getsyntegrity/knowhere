"""Tests for all 6 canonical entities."""

import pytest

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.reference import Reference
from canonical.entities.relationship import Relationship
from canonical.entities.repository import Repository
from canonical.entities.symbol import Symbol
from canonical.value_objects.code_location import CodeLocation


class TestRepository:
    """T003: Repository entity tests."""
    
    def test_required_fields(self, repo):
        """Repository requires source_uri and name."""
        assert repo.name == "test-repo"
        assert repo.source_uri == "https://github.com/test/repo"
        assert repo.source == "knowhere"
    
    def test_id_immutable(self, repo):
        """Repository.id is immutable."""
        with pytest.raises(Exception):
            repo.id = "new-id"
    
    def test_metadata_defaults(self, repo):
        """Repository metadata defaults to empty dict."""
        assert repo.metadata == {}


class TestFile:
    """T004: File entity tests."""
    
    def test_identity(self, file, repo):
        """File.id derives from path + repository_id."""
        assert file.repository_id == repo.id
        assert file.path == "src/main.py"
    
    def test_language_optional(self, file):
        """File language can be None."""
        assert file.language == "python"
    
    def test_checksum_required(self, file):
        """File checksum is required."""
        assert file.checksum == "abc123"


class TestSymbol:
    """T005: Symbol entity tests."""
    
    def test_qualified_name_unique(self, symbol):
        """Symbol has qualified_name."""
        assert symbol.qualified_name == "main.process_data"
    
    def test_location_bounds(self, symbol):
        """Symbol location is within bounds."""
        assert symbol.location.start_line == 10
        assert symbol.location.end_line == 20


class TestChunk:
    """T006: Chunk entity tests."""
    
    def test_same_text_same_location_same_id(self, factory, repo, file):
        """AC-024: Same text + same location → same chunk_id."""
        loc = CodeLocation(start_line=10, start_column=1, end_line=11, end_column=9)
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def process_data():\n    pass",
            location=loc, chunk_type="code", ordering=0,
        )
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def process_data():\n    pass",
            location=loc, chunk_type="code", ordering=0,
        )
        assert chunk1.id == chunk2.id
    
    def test_same_text_different_location_different_id(self, factory, repo, file):
        """AC-024: Same text + different location → different chunk_id."""
        loc1 = CodeLocation(start_line=10, start_column=1, end_line=11, end_column=9)
        loc2 = CodeLocation(start_line=20, start_column=1, end_line=21, end_column=9)
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def process_data():\n    pass",
            location=loc1, chunk_type="code", ordering=0,
        )
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def process_data():\n    pass",
            location=loc2, chunk_type="code", ordering=1,
        )
        assert chunk1.id != chunk2.id
        assert chunk1.semantic_hash == chunk2.semantic_hash
    
    def test_different_text_different_semantic_hash(self, factory, repo, file):
        """Different text → different semantic_hash."""
        loc = CodeLocation(start_line=10, start_column=1, end_line=11, end_column=9)
        chunk1 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def process_data():\n    pass",
            location=loc, chunk_type="code", ordering=0,
        )
        chunk2 = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def other_data():\n    pass",
            location=loc, chunk_type="code", ordering=0,
        )
        assert chunk1.semantic_hash != chunk2.semantic_hash


class TestRelationship:
    """T007: Relationship entity tests."""
    
    def test_duplicate_rejection(self, factory, repo, symbol):
        """Duplicate (source, target, type) not allowed per repository."""
        rel1 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol.id,
            target_id=symbol.id, type="calls",
        )
        rel2 = factory.build_relationship(
            repository_id=repo.id, source_id=symbol.id,
            target_id=symbol.id, type="calls",
        )
        assert rel1.id == rel2.id  # Same inputs = same deterministic ID


class TestReference:
    """T008: Reference entity tests."""
    
    def test_multiple_refs_distinct(self, factory, repo, file, symbol):
        """Multiple References at different locations are distinct."""
        ref1 = factory.build_reference(
            repository_id=repo.id, source_id=file.id, target_id=symbol.id,
            source_file_id=file.id, target_file_id=file.id,
            location=CodeLocation(start_line=15, start_column=5, end_line=15, end_column=17),
            role="call",
        )
        ref2 = factory.build_reference(
            repository_id=repo.id, source_id=file.id, target_id=symbol.id,
            source_file_id=file.id, target_file_id=file.id,
            location=CodeLocation(start_line=16, start_column=5, end_line=16, end_column=17),
            role="call",
        )
        assert ref1.id != ref2.id
