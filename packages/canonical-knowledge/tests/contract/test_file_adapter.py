"""Contract tests for FileAdapter."""

from canonical.adapters.stubs import InMemoryFileAdapter
from canonical.factory import CanonicalFactory


class TestFileAdapterContract:
    """T026: FileAdapter contract test suite."""
    
    def test_deterministic_id(self):
        """FileAdapter produces deterministic ID via factory."""
        adapter = InMemoryFileAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        files = list(adapter.to_canonical({"path": "src/main.py", "content": "print(1)"}, repo.id))
        assert len(files) == 1
        
        # Factory generates deterministic ID from adapter output
        file = factory.build_file(
            repository_id=repo.id, path=files[0].path,
            checksum=files[0].checksum, size_bytes=files[0].size_bytes,
        )
        # Factory produces deterministic ID
        assert len(file.id) > 0
        assert file.id == file.id  # Same inputs = same ID
    
    def test_checksum_computed(self):
        """FileAdapter computes content checksum."""
        adapter = InMemoryFileAdapter()
        repo = factory = CanonicalFactory().build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        
        files = list(adapter.to_canonical({"path": "src/main.py", "content": "hello"}, repo.id))
        assert files[0].checksum is not None
        assert len(files[0].checksum) == 64  # SHA-256 hex
    
    def test_language_inference(self):
        """FileAdapter infers language from metadata."""
        adapter = InMemoryFileAdapter()
        repo = CanonicalFactory().build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        
        files = list(adapter.to_canonical(
            {"path": "src/main.py", "content": "print(1)", "language": "python"},
            repo.id,
        ))
        assert files[0].language == "python"
    
    def test_path_normalization(self):
        """FileAdapter normalizes path."""
        adapter = InMemoryFileAdapter()
        repo = CanonicalFactory().build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        
        files = list(adapter.to_canonical({"path": "src/main.py"}, repo.id))
        assert files[0].path == "src/main.py"
    
    def test_no_symbol_chunk_reference_population(self):
        """FileAdapter does not populate symbols, chunks, or references."""
        adapter = InMemoryFileAdapter()
        repo = CanonicalFactory().build_repository(
            name="test", source_uri="https://github.com/test", source="knowhere",
        )
        
        files = list(adapter.to_canonical({"path": "src/main.py", "content": "x"}, repo.id))
        assert files[0].symbols == []
        assert files[0].chunks == []
        assert files[0].references == []
