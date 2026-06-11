"""In-memory adapter stubs for contract test validation."""

from abc import ABC, abstractmethod
from typing import Any, Iterable

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.relationship import Relationship
from canonical.entities.symbol import Symbol


class BaseAdapter(ABC):
    """Base adapter with common utilities."""
    
    @staticmethod
    def _compute_checksum(content: str | bytes) -> str:
        import hashlib
        if isinstance(content, str):
            return hashlib.sha256(content.encode("utf-8")).hexdigest()
        return hashlib.sha256(content).hexdigest()


class InMemoryFileAdapter(BaseAdapter):
    """Stub FileAdapter for testing."""
    
    def to_canonical(self, provider_input: dict, repository_id: str) -> Iterable[File]:
        """Convert dict to canonical File."""
        content = provider_input.get("content", "")
        yield File(
            id="",  # Will be computed by factory
            repository_id=repository_id,
            path=provider_input["path"],
            language=provider_input.get("language"),
            checksum=self._compute_checksum(content),
            size_bytes=len(content.encode("utf-8")),
        )


class InMemorySymbolAdapter(BaseAdapter):
    """Stub SymbolAdapter for testing."""
    
    def to_canonical(self, provider_input: dict, file_id: str, repository_id: str) -> Iterable[Symbol]:
        """Convert dict to canonical Symbol."""
        from canonical.value_objects.code_location import CodeLocation
        yield Symbol(
            id="",  # Will be computed by factory
            file_id=file_id,
            repository_id=repository_id,
            name=provider_input["name"],
            qualified_name=provider_input["qualified_name"],
            kind=provider_input.get("kind", "unknown"),
            location=CodeLocation(
                start_line=provider_input.get("start_line", 1),
                start_column=provider_input.get("start_column", 1),
                end_line=provider_input.get("end_line", 1),
                end_column=provider_input.get("end_column", 1),
            ),
        )


class InMemoryChunkAdapter(BaseAdapter):
    """Stub ChunkAdapter for testing."""
    
    def to_canonical(self, provider_input: dict, file_id: str, repository_id: str) -> Iterable[Chunk]:
        """Convert dict to canonical Chunk."""
        from canonical.value_objects.code_location import CodeLocation
        import hashlib
        text = provider_input["text"]
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        yield Chunk(
            id="",  # Will be computed by factory
            file_id=file_id,
            repository_id=repository_id,
            text=text,
            location=CodeLocation(
                start_line=provider_input.get("start_line", 1),
                start_column=provider_input.get("start_column", 1),
                end_line=provider_input.get("end_line", 1),
                end_column=provider_input.get("end_column", 1),
            ),
            semantic_hash=text_hash,
            chunk_type=provider_input.get("chunk_type", "unknown"),
            checksum=text_hash,
            ordering=provider_input.get("ordering", 0),
        )


class InMemoryRelationshipAdapter(BaseAdapter):
    """Stub RelationshipAdapter for testing."""
    
    def to_canonical(self, provider_input: dict, repository_id: str) -> Iterable[Relationship]:
        """Convert dict to canonical Relationship."""
        yield Relationship(
            id="",  # Will be computed by factory
            repository_id=repository_id,
            source_id=provider_input["source_id"],
            target_id=provider_input["target_id"],
            type=provider_input["type"],
            weight=provider_input.get("weight"),
        )
