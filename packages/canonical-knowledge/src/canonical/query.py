"""CanonicalRepository — in-memory query/navigation interface."""

from typing import Any

from canonical.entities.chunk import Chunk
from canonical.entities.file import File
from canonical.entities.reference import Reference
from canonical.entities.relationship import Relationship
from canonical.entities.repository import Repository
from canonical.entities.symbol import Symbol
from canonical.exceptions import CanonicalError


class CanonicalRepository:
    """In-memory query abstraction for canonical entities.
    
    Backend-agnostic. Operates on entity collections passed at construction time.
    Direct retrieval of child entities is a navigation convenience; it does not
    imply independent lifecycle, ownership, or persistence outside Repository.
    """
    
    def __init__(
        self,
        repository: Repository,
        files: list[File] | None = None,
        symbols: list[Symbol] | None = None,
        chunks: list[Chunk] | None = None,
        relationships: list[Relationship] | None = None,
        references: list[Reference] | None = None,
    ):
        self._repository = repository
        self._files = {f.id: f for f in (files or [])}
        self._symbols = {s.id: s for s in (symbols or [])}
        self._chunks = {c.id: c for c in (chunks or [])}
        self._relationships = {r.id: r for r in (relationships or [])}
        self._references = {ref.id: ref for ref in (references or [])}
        
        # Index by file_id for discovery
        self._symbols_by_file: dict[str, list[Symbol]] = {}
        for s in (symbols or []):
            self._symbols_by_file.setdefault(s.file_id, []).append(s)
        
        self._chunks_by_file: dict[str, list[Chunk]] = {}
        for c in (chunks or []):
            self._chunks_by_file.setdefault(c.file_id, []).append(c)
        
        self._references_by_file: dict[str, list[Reference]] = {}
        for ref in (references or []):
            self._references_by_file.setdefault(ref.source_file_id, []).append(ref)
        
        # Index relationships by source and target
        self._relationships_by_source: dict[str, list[Relationship]] = {}
        self._relationships_by_target: dict[str, list[Relationship]] = {}
        for r in (relationships or []):
            self._relationships_by_source.setdefault(r.source_id, []).append(r)
            self._relationships_by_target.setdefault(r.target_id, []).append(r)
    
    def get_repository(self, repository_id: str) -> Repository:
        """Return Repository by ID."""
        if self._repository.id != repository_id:
            raise CanonicalError(f"Repository not found: {repository_id}")
        return self._repository
    
    def get_file(self, file_id: str) -> File:
        """Return File by ID."""
        if file_id not in self._files:
            raise CanonicalError(f"File not found: {file_id}")
        return self._files[file_id]
    
    def get_symbol(self, symbol_id: str) -> Symbol:
        """Return Symbol by ID."""
        if symbol_id not in self._symbols:
            raise CanonicalError(f"Symbol not found: {symbol_id}")
        return self._symbols[symbol_id]
    
    def get_chunk(self, chunk_id: str) -> Chunk:
        """Return Chunk by ID."""
        if chunk_id not in self._chunks:
            raise CanonicalError(f"Chunk not found: {chunk_id}")
        return self._chunks[chunk_id]
    
    def get_relationship(self, relationship_id: str) -> Relationship:
        """Return Relationship by ID."""
        if relationship_id not in self._relationships:
            raise CanonicalError(f"Relationship not found: {relationship_id}")
        return self._relationships[relationship_id]
    
    def get_reference(self, reference_id: str) -> Reference:
        """Return Reference by ID."""
        if reference_id not in self._references:
            raise CanonicalError(f"Reference not found: {reference_id}")
        return self._references[reference_id]
    
    def find_symbols(self, file_id: str) -> list[Symbol]:
        """Return all Symbols defined in the given File."""
        return self._symbols_by_file.get(file_id, [])
    
    def find_chunks(self, file_id: str) -> list[Chunk]:
        """Return all Chunks extracted from the given File, in ordering."""
        chunks = self._chunks_by_file.get(file_id, [])
        return sorted(chunks, key=lambda c: c.ordering)
    
    def find_references(self, file_id: str) -> list[Reference]:
        """Return all References originating in the given File."""
        return self._references_by_file.get(file_id, [])
    
    def find_relationships(self, source_id: str) -> list[Relationship]:
        """Return all Relationships with the given source_id."""
        return self._relationships_by_source.get(source_id, [])
    
    def find_relationships_by_target(self, target_id: str) -> list[Relationship]:
        """Return all Relationships with the given target_id."""
        return self._relationships_by_target.get(target_id, [])
    
    def find_entities_by_type(self, entity_type: str) -> list[Any]:
        """Return all entities of a given type within the Repository."""
        mapping = {
            "file": list(self._files.values()),
            "symbol": list(self._symbols.values()),
            "chunk": list(self._chunks.values()),
            "relationship": list(self._relationships.values()),
            "reference": list(self._references.values()),
        }
        return mapping.get(entity_type, [])
    
    def get_file_by_path(self, repository_id: str, path: str) -> File:
        """Return a File by its repository-relative path."""
        self.get_repository(repository_id)  # Verify repository exists
        for file in self._files.values():
            if file.path == path:
                return file
        raise CanonicalError(f"File not found at path: {path}")
    
    def get_symbol_by_name(self, repository_id: str, qualified_name: str) -> Symbol:
        """Return a Symbol by its qualified name."""
        self.get_repository(repository_id)  # Verify repository exists
        for symbol in self._symbols.values():
            if symbol.qualified_name == qualified_name:
                return symbol
        raise CanonicalError(f"Symbol not found with qualified_name: {qualified_name}")
