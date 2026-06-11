"""
GraphProvider Interface
=======================

Interface for graph storage providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.graph import GraphNode, GraphEdge
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class GraphProvider(ABC):
    """Interface for graph storage providers."""
    
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
        """Validate the consistency of the graph storage."""
        pass
    
    # Node operations
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
    
    # Edge operations
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
    
    # Graph operations
    @abstractmethod
    def get_node_neighbors(self, node_id: UUID, direction: str = "both") -> List[UUID]:
        """Get neighbors of a node."""
        pass
    
    @abstractmethod
    def get_node_degree(self, node_id: UUID) -> Dict[str, int]:
        """Get the degree of a node."""
        pass
    
    @abstractmethod
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get statistics about the graph."""
        pass