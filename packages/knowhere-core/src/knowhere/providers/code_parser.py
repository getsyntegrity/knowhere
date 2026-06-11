"""
CodeParserProvider Interface
============================

Interface for code parsing providers in the Knowhere system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID

from ..entities.code import File, Symbol, Dependency, Reference
from ..types.metrics import Capability, MetricReport, ConsistencyReport


class CodeParserProvider(ABC):
    """Interface for code parsing providers."""
    
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
        """Validate the consistency of the code parser."""
        pass
    
    @abstractmethod
    def parse_file(self, file_content: str, language: str) -> List[Symbol]:
        """Parse a file and return its symbols."""
        pass
    
    @abstractmethod
    def extract_dependencies(self, file_content: str, language: str) -> List[Dependency]:
        """Extract dependencies from a file."""
        pass
    
    @abstractmethod
    def find_references(self, file_content: str, symbol_name: str, language: str) -> List[Reference]:
        """Find references to a symbol in a file."""
        pass
    
    @abstractmethod
    def get_file_language(self, file_path: str) -> str:
        """Determine the language of a file based on its path."""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages."""
        pass