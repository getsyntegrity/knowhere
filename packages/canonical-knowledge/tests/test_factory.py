"""Tests for CanonicalFactory."""

import pytest

from canonical.exceptions import ValidationError
from canonical.factory import CanonicalFactory
from canonical.value_objects.code_location import CodeLocation


class TestCanonicalFactory:
    """T020: CanonicalFactory tests."""
    
    def test_missing_required_fields(self):
        """Missing required fields → error."""
        factory = CanonicalFactory()
        with pytest.raises(TypeError):
            factory.build_repository(name="test")  # Missing source_uri and source
    
    def test_invalid_field_values(self):
        """Invalid field values → error."""
        factory = CanonicalFactory()
        with pytest.raises(ValueError):
            factory.build_file(
                repository_id="repo-123", path="src/main.py",
                checksum="abc", size_bytes=-1,  # Negative size
            )
    
    def test_atomic_batch(self):
        """Atomic batch: all pass or none."""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        # This should succeed
        batch = factory.build_batch([repo, file])
        assert len(batch) == 2
    
    def test_duplicate_ids_within_batch(self):
        """Duplicate IDs within batch → error."""
        factory = CanonicalFactory()
        repo1 = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        repo2 = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        with pytest.raises(Exception):
            factory.build_batch([repo1, repo2])
    
    def test_cross_entity_reference_validation(self):
        """Cross-entity reference validation."""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        # This should succeed (forward reference within batch)
        batch = factory.build_batch([repo, file, symbol])
        assert len(batch) == 3
    
    def test_chunk_semantic_hash(self):
        """Chunk semantic_hash is computed correctly."""
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        chunk = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def hello():\n    pass",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        
        import hashlib
        expected_hash = hashlib.sha256("def hello():\n    pass".encode("utf-8")).hexdigest()
        assert chunk.semantic_hash == expected_hash
        assert chunk.checksum == expected_hash
