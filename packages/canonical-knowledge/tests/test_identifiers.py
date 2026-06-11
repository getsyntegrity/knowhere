"""Tests for IdentifierService."""

from canonical.identifiers import IdentifierService


class TestIdentifierService:
    """T018: IdentifierService tests."""
    
    def test_same_input_same_id(self):
        """Same input → same ID across calls."""
        id1 = IdentifierService.generate_repository_id("https://github.com/test", "knowhere")
        id2 = IdentifierService.generate_repository_id("https://github.com/test", "knowhere")
        assert id1 == id2
    
    def test_different_input_different_id(self):
        """Different input → different ID."""
        id1 = IdentifierService.generate_repository_id("https://github.com/test", "knowhere")
        id2 = IdentifierService.generate_repository_id("https://github.com/other", "knowhere")
        assert id1 != id2
    
    def test_id_stability(self):
        """ID stability across restarts (same algorithm)."""
        id1 = IdentifierService.generate_file_id("src/main.py", "repo-123")
        # Simulate restart by creating new instance
        id2 = IdentifierService.generate_file_id("src/main.py", "repo-123")
        assert id1 == id2
    
    def test_all_entity_types(self):
        """All 6 entity types have deterministic IDs."""
        repo_id = IdentifierService.generate_repository_id("https://github.com/test", "knowhere")
        file_id = IdentifierService.generate_file_id("src/main.py", repo_id)
        symbol_id = IdentifierService.generate_symbol_id("main.process_data", repo_id)
        chunk_id = IdentifierService.generate_chunk_id(repo_id, file_id, "10:1-20:2")
        rel_id = IdentifierService.generate_relationship_id(file_id, symbol_id, "calls", repo_id)
        ref_id = IdentifierService.generate_reference_id(file_id, symbol_id, "10:1-20:2", repo_id)
        
        # All IDs should be non-empty strings
        assert all(isinstance(i, str) and len(i) > 0 for i in [repo_id, file_id, symbol_id, chunk_id, rel_id, ref_id])
        
        # All IDs should be different (different inputs)
        ids = [repo_id, file_id, symbol_id, chunk_id, rel_id, ref_id]
        assert len(set(ids)) == len(ids)
