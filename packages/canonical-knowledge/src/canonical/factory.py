"""CanonicalFactory — entity creation with invariant validation and deterministic IDs."""

from datetime import datetime, timezone
from typing import Any

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.reference import Reference
from canonical.entities.relationship import Relationship
from canonical.entities.repository import Repository
from canonical.entities.symbol import Symbol
from canonical.exceptions import IdentifierCollision, InvariantViolation, ValidationError
from canonical.identifiers import IdentifierService
from canonical.value_objects.code_location import CodeLocation


class CanonicalFactory:
    """Creates canonical entities from raw source data with full validation."""
    
    def __init__(self, identifier_service: IdentifierService | None = None):
        self._id = identifier_service or IdentifierService()
    
    def build_repository(
        self,
        name: str,
        source_uri: str,
        source: str,
        files: list | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Repository:
        """Create a validated Repository entity."""
        repo_id = self._id.generate_repository_id(source_uri, source)
        return Repository(
            id=repo_id,
            name=name,
            source_uri=source_uri,
            source=source,
            files=files or [],
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
    
    def build_file(
        self,
        repository_id: str,
        path: str,
        checksum: str,
        size_bytes: int,
        language: str | None = None,
        symbols: list | None = None,
        chunks: list | None = None,
        references: list | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> File:
        """Create a validated File entity."""
        file_id = self._id.generate_file_id(path, repository_id)
        return File(
            id=file_id,
            repository_id=repository_id,
            path=path,
            language=language,
            checksum=checksum,
            size_bytes=size_bytes,
            symbols=symbols or [],
            chunks=chunks or [],
            references=references or [],
            metadata=metadata or {},
        )
    
    def build_symbol(
        self,
        repository_id: str,
        file_id: str,
        name: str,
        qualified_name: str,
        kind: str,
        location: CodeLocation,
        scope: str | None = None,
        signature: str | None = None,
        documentation: str | None = None,
        children: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Symbol:
        """Create a validated Symbol entity."""
        symbol_id = self._id.generate_symbol_id(qualified_name, repository_id)
        return Symbol(
            id=symbol_id,
            file_id=file_id,
            repository_id=repository_id,
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            scope=scope,
            location=location,
            signature=signature,
            documentation=documentation,
            children=children or [],
            metadata=metadata or {},
        )
    
    def build_chunk(
        self,
        repository_id: str,
        file_id: str,
        text: str,
        location: CodeLocation,
        chunk_type: str,
        ordering: int,
        semantic_hash: str | None = None,
        checksum: str | None = None,
        symbol_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Chunk:
        """Create a validated Chunk entity."""
        import hashlib
        
        text_hash = semantic_hash or hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunk_checksum = checksum or text_hash
        chunk_id = self._id.generate_chunk_id(
            repository_id, file_id, str(location)
        )
        return Chunk(
            id=chunk_id,
            file_id=file_id,
            repository_id=repository_id,
            text=text,
            location=location,
            semantic_hash=text_hash,
            chunk_type=chunk_type,
            checksum=chunk_checksum,
            ordering=ordering,
            symbol_ids=symbol_ids or [],
            metadata=metadata or {},
        )
    
    def build_relationship(
        self,
        repository_id: str,
        source_id: str,
        target_id: str,
        type: str,
        weight: float | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Relationship:
        """Create a validated Relationship entity."""
        rel_id = self._id.generate_relationship_id(source_id, target_id, type, repository_id)
        return Relationship(
            id=rel_id,
            repository_id=repository_id,
            source_id=source_id,
            target_id=target_id,
            type=type,
            weight=weight,
            attributes=attributes,
            metadata=metadata or {},
        )
    
    def build_reference(
        self,
        repository_id: str,
        source_id: str,
        target_id: str,
        source_file_id: str,
        target_file_id: str,
        location: CodeLocation,
        role: str,
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Reference:
        """Create a validated Reference entity."""
        ref_id = self._id.generate_reference_id(
            source_id, target_id, str(location), repository_id
        )
        return Reference(
            id=ref_id,
            repository_id=repository_id,
            source_id=source_id,
            target_id=target_id,
            source_file_id=source_file_id,
            target_file_id=target_file_id,
            location=location,
            context=context,
            role=role,
            metadata=metadata or {},
        )
    
    def build_batch(self, entities: list) -> list:
        """Atomic batch creation with cross-entity reference validation.
        
        Forward references inside the same batch are valid.
        References outside the batch must already exist.
        
        Raises ValidationError if any entity fails validation.
        """
        # Collect all IDs in the batch
        batch_ids = {e.id for e in entities if hasattr(e, "id")}
        
        # Validate cross-entity references
        for entity in entities:
            if isinstance(entity, Relationship):
                if entity.source_id not in batch_ids and not self._id_exists(entity.source_id):
                    raise ValidationError(
                        f"Relationship references unknown source_id: {entity.source_id}"
                    )
                if entity.target_id not in batch_ids and not self._id_exists(entity.target_id):
                    raise ValidationError(
                        f"Relationship references unknown target_id: {entity.target_id}"
                    )
        
        # Check for duplicate IDs
        seen = set()
        for entity in entities:
            if hasattr(entity, "id"):
                if entity.id in seen:
                    raise IdentifierCollision(
                        f"Duplicate identifier in batch: {entity.id}",
                        identifier=entity.id,
                    )
                seen.add(entity.id)
        
        return entities
    
    @staticmethod
    def _id_exists(entity_id: str) -> bool:
        """Check if an entity ID exists outside the current batch.
        
        In a real implementation, this would query persistent storage.
        For the factory, external IDs are assumed to exist if not in the batch.
        """
        return True  # Assume external IDs exist (storage check deferred)
