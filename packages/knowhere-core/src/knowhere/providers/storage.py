"""
StorageProvider Interface
=========================

Interface for storage providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.source import KnowledgeSource
from ..entities.chunk import KnowledgeChunk
from ..entities.version import KnowledgeVersion
from ..entities.pipeline import RetrievalPipeline
from ..entities.graph import GraphNode, GraphEdge
from ..entities.memory import Memory, MemoryFact, MemoryRelationship, MemorySummary
from ..entities.code import Repository, File, Symbol, Dependency, Reference
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class StorageProvider(ABC):
    """Interface for storage providers."""
    
    @abstractmethod
    def get_capability(self) -> Capability:
        """Get the capability of this provider."""
        pass
    
    @abstractmethod
    def get_metrics(self) -> MetricReport:
        """Get metrics for this provider."""
        pass
    
    @abstractmethod
    def validate_consistency(self) -> ConsistencyReport:
        """Validate the consistency of the storage."""
        pass
    
    # KnowledgeSource operations
    @abstractmethod
    def create_source(self, source: KnowledgeSource) -> KnowledgeSource:
        """Create a new knowledge source."""
        pass
    
    @abstractmethod
    def get_source(self, source_id: UUID) -> Optional[KnowledgeSource]:
        """Get a knowledge source by ID."""
        pass
    
    @abstractmethod
    def list_sources(self, **filters) -> List[KnowledgeSource]:
        """List knowledge sources with optional filters."""
        pass
    
    @abstractmethod
    def update_source(self, source_id: UUID, updates: Dict[str, Any]) -> KnowledgeSource:
        """Update a knowledge source."""
        pass
    
    @abstractmethod
    def delete_source(self, source_id: UUID) -> bool:
        """Delete a knowledge source."""
        pass
    
    # KnowledgeChunk operations
    @abstractmethod
    def create_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        """Create a new knowledge chunk."""
        pass
    
    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Optional[KnowledgeChunk]:
        """Get a knowledge chunk by ID."""
        pass
    
    @abstractmethod
    def list_chunks(self, **filters) -> List[KnowledgeChunk]:
        """List knowledge chunks with optional filters."""
        pass
    
    @abstractmethod
    def update_chunk(self, chunk_id: str, updates: Dict[str, Any]) -> KnowledgeChunk:
        """Update a knowledge chunk."""
        pass
    
    @abstractmethod
    def delete_chunk(self, chunk_id: str) -> bool:
        """Delete a knowledge chunk."""
        pass
    
    # KnowledgeVersion operations
    @abstractmethod
    def create_version(self, version: KnowledgeVersion) -> KnowledgeVersion:
        """Create a new knowledge version."""
        pass
    
    @abstractmethod
    def get_version(self, version_id: UUID) -> Optional[KnowledgeVersion]:
        """Get a knowledge version by ID."""
        pass
    
    @abstractmethod
    def list_versions(self, **filters) -> List[KnowledgeVersion]:
        """List knowledge versions with optional filters."""
        pass
    
    @abstractmethod
    def update_version(self, version_id: UUID, updates: Dict[str, Any]) -> KnowledgeVersion:
        """Update a knowledge version."""
        pass
    
    @abstractmethod
    def delete_version(self, version_id: UUID) -> bool:
        """Delete a knowledge version."""
        pass
    
    # RetrievalPipeline operations
    @abstractmethod
    def create_pipeline(self, pipeline: RetrievalPipeline) -> RetrievalPipeline:
        """Create a new retrieval pipeline."""
        pass
    
    @abstractmethod
    def get_pipeline(self, pipeline_id: UUID) -> Optional[RetrievalPipeline]:
        """Get a retrieval pipeline by ID."""
        pass
    
    @abstractmethod
    def list_pipelines(self, **filters) -> List[RetrievalPipeline]:
        """List retrieval pipelines with optional filters."""
        pass
    
    @abstractmethod
    def update_pipeline(self, pipeline_id: UUID, updates: Dict[str, Any]) -> RetrievalPipeline:
        """Update a retrieval pipeline."""
        pass
    
    @abstractmethod
    def delete_pipeline(self, pipeline_id: UUID) -> bool:
        """Delete a retrieval pipeline."""
        pass
    
    # Graph operations
    @abstractmethod
    def create_node(self, node: GraphNode) -> GraphNode:
        """Create a new graph node."""
        pass
    
    @abstractmethod
    def get_node(self, node_id: UUID) -> Optional[GraphNode]:
        """Get a graph node by ID."""
        pass
    
    @abstractmethod
    def list_nodes(self, **filters) -> List[GraphNode]:
        """List graph nodes with optional filters."""
        pass
    
    @abstractmethod
    def update_node(self, node_id: UUID, updates: Dict[str, Any]) -> GraphNode:
        """Update a graph node."""
        pass
    
    @abstractmethod
    def delete_node(self, node_id: UUID) -> bool:
        """Delete a graph node."""
        pass
    
    @abstractmethod
    def create_edge(self, edge: GraphEdge) -> GraphEdge:
        """Create a new graph edge."""
        pass
    
    @abstractmethod
    def get_edge(self, edge_id: UUID) -> Optional[GraphEdge]:
        """Get a graph edge by ID."""
        pass
    
    @abstractmethod
    def list_edges(self, **filters) -> List[GraphEdge]:
        """List graph edges with optional filters."""
        pass
    
    @abstractmethod
    def update_edge(self, edge_id: UUID, updates: Dict[str, Any]) -> GraphEdge:
        """Update a graph edge."""
        pass
    
    @abstractmethod
    def delete_edge(self, edge_id: UUID) -> bool:
        """Delete a graph edge."""
        pass
    
    # Memory operations
    @abstractmethod
    def create_memory(self, memory: Memory) -> Memory:
        """Create a new memory."""
        pass
    
    @abstractmethod
    def get_memory(self, memory_id: UUID) -> Optional[Memory]:
        """Get a memory by ID."""
        pass
    
    @abstractmethod
    def list_memories(self, **filters) -> List[Memory]:
        """List memories with optional filters."""
        pass
    
    @abstractmethod
    def update_memory(self, memory_id: UUID, updates: Dict[str, Any]) -> Memory:
        """Update a memory."""
        pass
    
    @abstractmethod
    def delete_memory(self, memory_id: UUID) -> bool:
        """Delete a memory."""
        pass
    
    @abstractmethod
    def create_fact(self, fact: MemoryFact) -> MemoryFact:
        """Create a new memory fact."""
        pass
    
    @abstractmethod
    def get_fact(self, fact_id: UUID) -> Optional[MemoryFact]:
        """Get a memory fact by ID."""
        pass
    
    @abstractmethod
    def list_facts(self, **filters) -> List[MemoryFact]:
        """List memory facts with optional filters."""
        pass
    
    @abstractmethod
    def update_fact(self, fact_id: UUID, updates: Dict[str, Any]) -> MemoryFact:
        """Update a memory fact."""
        pass
    
    @abstractmethod
    def delete_fact(self, fact_id: UUID) -> bool:
        """Delete a memory fact."""
        pass
    
    @abstractmethod
    def create_relationship(self, relationship: MemoryRelationship) -> MemoryRelationship:
        """Create a new memory relationship."""
        pass
    
    @abstractmethod
    def get_relationship(self, relationship_id: UUID) -> Optional[MemoryRelationship]:
        """Get a memory relationship by ID."""
        pass
    
    @abstractmethod
    def list_relationships(self, **filters) -> List[MemoryRelationship]:
        """List memory relationships with optional filters."""
        pass
    
    @abstractmethod
    def update_relationship(self, relationship_id: UUID, updates: Dict[str, Any]) -> MemoryRelationship:
        """Update a memory relationship."""
        pass
    
    @abstractmethod
    def delete_relationship(self, relationship_id: UUID) -> bool:
        """Delete a memory relationship."""
        pass
    
    @abstractmethod
    def create_summary(self, summary: MemorySummary) -> MemorySummary:
        """Create a new memory summary."""
        pass
    
    @abstractmethod
    def get_summary(self, summary_id: UUID) -> Optional[MemorySummary]:
        """Get a memory summary by ID."""
        pass
    
    @abstractmethod
    def list_summaries(self, **filters) -> List[MemorySummary]:
        """List memory summaries with optional filters."""
        pass
    
    @abstractmethod
    def update_summary(self, summary_id: UUID, updates: Dict[str, Any]) -> MemorySummary:
        """Update a memory summary."""
        pass
    
    @abstractmethod
    def delete_summary(self, summary_id: UUID) -> bool:
        """Delete a memory summary."""
        pass
    
    # Code operations
    @abstractmethod
    def create_repository(self, repository: Repository) -> Repository:
        """Create a new repository."""
        pass
    
    @abstractmethod
    def get_repository(self, repository_id: UUID) -> Optional[Repository]:
        """Get a repository by ID."""
        pass
    
    @abstractmethod
    def list_repositories(self, **filters) -> List[Repository]:
        """List repositories with optional filters."""
        pass
    
    @abstractmethod
    def update_repository(self, repository_id: UUID, updates: Dict[str, Any]) -> Repository:
        """Update a repository."""
        pass
    
    @abstractmethod
    def delete_repository(self, repository_id: UUID) -> bool:
        """Delete a repository."""
        pass
    
    @abstractmethod
    def create_file(self, file: File) -> File:
        """Create a new file."""
        pass
    
    @abstractmethod
    def get_file(self, file_id: UUID) -> Optional[File]:
        """Get a file by ID."""
        pass
    
    @abstractmethod
    def list_files(self, **filters) -> List[File]:
        """List files with optional filters."""
        pass
    
    @abstractmethod
    def update_file(self, file_id: UUID, updates: Dict[str, Any]) -> File:
        """Update a file."""
        pass
    
    @abstractmethod
    def delete_file(self, file_id: UUID) -> bool:
        """Delete a file."""
        pass
    
    @abstractmethod
    def create_symbol(self, symbol: Symbol) -> Symbol:
        """Create a new symbol."""
        pass
    
    @abstractmethod
    def get_symbol(self, symbol_id: UUID) -> Optional[Symbol]:
        """Get a symbol by ID."""
        pass
    
    @abstractmethod
    def list_symbols(self, **filters) -> List[Symbol]:
        """List symbols with optional filters."""
        pass
    
    @abstractmethod
    def update_symbol(self, symbol_id: UUID, updates: Dict[str, Any]) -> Symbol:
        """Update a symbol."""
        pass
    
    @abstractmethod
    def delete_symbol(self, symbol_id: UUID) -> bool:
        """Delete a symbol."""
        pass
    
    @abstractmethod
    def create_dependency(self, dependency: Dependency) -> Dependency:
        """Create a new dependency."""
        pass
    
    @abstractmethod
    def get_dependency(self, dependency_id: UUID) -> Optional[Dependency]:
        """Get a dependency by ID."""
        pass
    
    @abstractmethod
    def list_dependencies(self, **filters) -> List[Dependency]:
        """List dependencies with optional filters."""
        pass
    
    @abstractmethod
    def update_dependency(self, dependency_id: UUID, updates: Dict[str, Any]) -> Dependency:
        """Update a dependency."""
        pass
    
    @abstractmethod
    def delete_dependency(self, dependency_id: UUID) -> bool:
        """Delete a dependency."""
        pass
    
    @abstractmethod
    def create_reference(self, reference: Reference) -> Reference:
        """Create a new reference."""
        pass
    
    @abstractmethod
    def get_reference(self, reference_id: UUID) -> Optional[Reference]:
        """Get a reference by ID."""
        pass
    
    @abstractmethod
    def list_references(self, **filters) -> List[Reference]:
        """List references with optional filters."""
        pass
    
    @abstractmethod
    def update_reference(self, reference_id: UUID, updates: Dict[str, Any]) -> Reference:
        """Update a reference."""
        pass
    
    @abstractmethod
    def delete_reference(self, reference_id: UUID) -> bool:
        """Delete a reference."""
        pass