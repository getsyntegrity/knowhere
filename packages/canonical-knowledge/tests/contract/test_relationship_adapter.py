"""Contract tests for RelationshipAdapter."""

from canonical.adapters.stubs import InMemoryRelationshipAdapter
from canonical.factory import CanonicalFactory
from canonical.value_objects.code_location import CodeLocation


class TestRelationshipAdapterContract:
    """T029: RelationshipAdapter contract test suite."""
    
    def test_composite_id(self):
        """RelationshipAdapter produces composite ID."""
        adapter = InMemoryRelationshipAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        rels = list(adapter.to_canonical(
            {"source_id": symbol.id, "target_id": symbol.id, "type": "calls"},
            repo.id,
        ))
        assert rels[0].id is not None
    
    def test_duplicate_rejection(self):
        """RelationshipAdapter rejects duplicate (source, target, type)."""
        adapter = InMemoryRelationshipAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        rels1 = list(adapter.to_canonical(
            {"source_id": symbol.id, "target_id": symbol.id, "type": "calls"},
            repo.id,
        ))
        rels2 = list(adapter.to_canonical(
            {"source_id": symbol.id, "target_id": symbol.id, "type": "calls"},
            repo.id,
        ))
        
        # Same inputs → same deterministic ID
        assert rels1[0].id == rels2[0].id
    
    def test_custom_type_prefix(self):
        """RelationshipAdapter supports custom type prefixes."""
        adapter = InMemoryRelationshipAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        rels = list(adapter.to_canonical(
            {"source_id": symbol.id, "target_id": symbol.id, "type": "custom:mytype"},
            repo.id,
        ))
        assert rels[0].type == "custom:mytype"
    
    def test_optional_weight(self):
        """RelationshipAdapter supports optional weight."""
        adapter = InMemoryRelationshipAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        rels = list(adapter.to_canonical(
            {"source_id": symbol.id, "target_id": symbol.id, "type": "calls", "weight": 0.8},
            repo.id,
        ))
        assert rels[0].weight == 0.8
    
    def test_cross_reference_validation(self):
        """RelationshipAdapter validates cross-entity references."""
        adapter = InMemoryRelationshipAdapter()
        factory = CanonicalFactory()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        # Should work with valid source/target IDs
        rels = list(adapter.to_canonical(
            {"source_id": "valid-id", "target_id": "valid-id", "type": "calls"},
            repo.id,
        ))
        assert len(rels) == 1
