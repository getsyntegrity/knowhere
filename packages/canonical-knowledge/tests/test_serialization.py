"""Tests for serialization."""

import pytest

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.reference import Reference
from canonical.entities.relationship import Relationship
from canonical.entities.repository import Repository
from canonical.entities.symbol import Symbol
from canonical.exceptions import SerializationError
from canonical.factory import CanonicalFactory
from canonical.serialization import JsonSerializer
from canonical.value_objects.code_location import CodeLocation


class TestJsonSerializer:
    """T022: Serialization tests."""
    
    def test_repository_roundtrip(self):
        """Repository serialization roundtrip."""
        factory = CanonicalFactory()
        serializer = JsonSerializer()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        json_str = serializer.to_json(repo)
        restored = serializer.from_json(json_str, Repository)
        
        assert restored.id == repo.id
        assert restored.name == repo.name
        assert restored.source_uri == repo.source_uri
    
    def test_file_roundtrip(self):
        """File serialization roundtrip."""
        factory = CanonicalFactory()
        serializer = JsonSerializer()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        
        json_str = serializer.to_json(file)
        restored = serializer.from_json(json_str, File)
        
        assert restored.id == file.id
        assert restored.path == file.path
    
    def test_version_marker_in_output(self):
        """Version marker is embedded in output."""
        serializer = JsonSerializer()
        repo = CanonicalFactory().build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        json_str = serializer.to_json(repo)
        assert "canonical_model_version" in json_str
    
    def test_major_version_mismatch(self):
        """Major version mismatch → error."""
        serializer = JsonSerializer()
        repo = CanonicalFactory().build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        
        json_str = serializer.to_json(repo)
        # Modify version to simulate future breaking change
        modified = json_str.replace("\"1.0.0\"", "\"2.0.0\"")
        
        with pytest.raises(SerializationError):
            serializer.from_json(modified, Repository)
    
    def test_symbol_roundtrip(self):
        """Symbol with CodeLocation serialization roundtrip."""
        factory = CanonicalFactory()
        serializer = JsonSerializer()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        
        json_str = serializer.to_json(symbol)
        restored = serializer.from_json(json_str, Symbol)
        
        assert restored.id == symbol.id
        assert restored.location.start_line == 1
        assert restored.location.end_column == 10
    
    def test_all_six_entity_types(self):
        """All 6 entity types can be serialized and deserialized."""
        factory = CanonicalFactory()
        serializer = JsonSerializer()
        repo = factory.build_repository(name="test", source_uri="https://github.com/test", source="knowhere")
        file = factory.build_file(repository_id=repo.id, path="src/main.py", checksum="abc", size_bytes=100)
        symbol = factory.build_symbol(
            repository_id=repo.id, file_id=file.id,
            name="process", qualified_name="main.process", kind="function",
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
        )
        chunk = factory.build_chunk(
            repository_id=repo.id, file_id=file.id,
            text="def process():\n    pass",
            location=CodeLocation(start_line=1, start_column=1, end_line=2, end_column=9),
            chunk_type="code", ordering=0,
        )
        rel = factory.build_relationship(
            repository_id=repo.id, source_id=symbol.id, target_id=symbol.id, type="calls",
        )
        ref = factory.build_reference(
            repository_id=repo.id, source_id=file.id, target_id=symbol.id,
            source_file_id=file.id, target_file_id=file.id,
            location=CodeLocation(start_line=1, start_column=1, end_line=1, end_column=10),
            role="call",
        )
        
        entities = [repo, file, symbol, chunk, rel, ref]
        for entity in entities:
            json_str = serializer.to_json(entity)
            restored = serializer.from_json(json_str, type(entity))
            assert restored.id == entity.id
