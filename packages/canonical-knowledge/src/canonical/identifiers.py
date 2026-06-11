"""IdentifierService — deterministic SHA-256 identifier generation."""

import hashlib
from uuid import uuid4


class IdentifierService:
    """Generates deterministic identifiers for canonical entities.
    
    All identifiers use SHA-256 of UTF-8 concatenated input fields with '|' separator.
    This is a permanent public contract — the algorithm and input composition rules
    MUST NOT change after release.
    """
    
    @staticmethod
    def _hash(inputs: list[str]) -> str:
        """Compute SHA-256 hash of concatenated inputs."""
        canonical = "|".join(inputs)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    
    @classmethod
    def generate_repository_id(cls, source_uri: str, source: str) -> str:
        """Generate Repository.id from source_uri + source."""
        return cls._hash([source_uri, source])
    
    @classmethod
    def generate_file_id(cls, path: str, repository_id: str) -> str:
        """Generate File.id from path + repository_id."""
        return cls._hash([path, repository_id])
    
    @classmethod
    def generate_symbol_id(cls, qualified_name: str, repository_id: str) -> str:
        """Generate Symbol.id from qualified_name + repository_id."""
        return cls._hash([qualified_name, repository_id])
    
    @classmethod
    def generate_chunk_id(cls, repository_id: str, file_id: str, location: str) -> str:
        """Generate Chunk.id from repository_id + file_id + location."""
        return cls._hash([repository_id, file_id, location])
    
    @classmethod
    def generate_relationship_id(
        cls, source_id: str, target_id: str, type: str, repository_id: str
    ) -> str:
        """Generate Relationship.id from source_id + target_id + type + repository_id."""
        return cls._hash([source_id, target_id, type, repository_id])
    
    @classmethod
    def generate_reference_id(
        cls, source_id: str, target_id: str, location: str, repository_id: str
    ) -> str:
        """Generate Reference.id from source_id + target_id + location + repository_id."""
        return cls._hash([source_id, target_id, location, repository_id])
    
    @staticmethod
    def generate_snapshot_id() -> str:
        """Generate non-deterministic Snapshot ID (UUID4)."""
        return str(uuid4())
