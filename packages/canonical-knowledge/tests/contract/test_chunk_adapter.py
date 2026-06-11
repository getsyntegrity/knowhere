"""Contract tests for ChunkAdapter."""

from canonical.adapters.stubs import InMemoryChunkAdapter
from canonical.factory import CanonicalFactory
from canonical.value_objects.code_location import CodeLocation


class TestChunkAdapterContract:
    """T028: ChunkAdapter contract test suite."""
    
    def test_composite_id(self):
        """ChunkAdapter produces composite ID."""
        adapter = InMemoryChunkAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        chunks = list(adapter.to_canonical(
            {
                "text": "def hello():\n    pass",
                "start_line": 1, "start_column": 1, "end_line": 2, "end_column": 9,
            },
            file.id, repo.id,
        ))
        assert chunks[0].id is not None
    
    def test_semantic_hash(self):
        """ChunkAdapter computes semantic_hash from text only."""
        adapter = InMemoryChunkAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        chunks = list(adapter.to_canonical(
            {"text": "hello world", "start_line": 1, "start_column": 1, "end_line": 1, "end_column": 11},
            file.id, repo.id,
        ))
        assert chunks[0].semantic_hash is not None
        assert len(chunks[0].semantic_hash) == 64
    
    def test_ordering(self):
        """ChunkAdapter assigns ordering."""
        adapter = InMemoryChunkAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        chunks = list(adapter.to_canonical(
            {"text": "a", "start_line": 1, "start_column": 1, "end_line": 1, "end_column": 1, "ordering": 5},
            file.id, repo.id,
        ))
        assert chunks[0].ordering == 5
    
    def test_chunk_type_mapping(self):
        """ChunkAdapter maps chunk_type."""
        adapter = InMemoryChunkAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        chunks = list(adapter.to_canonical(
            {
                "text": "# comment", "chunk_type": "comment",
                "start_line": 1, "start_column": 1, "end_line": 1, "end_column": 9,
            },
            file.id, repo.id,
        ))
        assert chunks[0].chunk_type == "comment"
    
    def test_no_embedding_leakage(self):
        """ChunkAdapter does not include embedding vectors."""
        adapter = InMemoryChunkAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        chunks = list(adapter.to_canonical(
            {"text": "hello", "start_line": 1, "start_column": 1, "end_line": 1, "end_column": 5},
            file.id, repo.id,
        ))
        # Chunk should not have any embedding-related fields
        assert not hasattr(chunks[0], "embedding")
        assert not hasattr(chunks[0], "vector")
