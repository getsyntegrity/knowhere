"""
Code Entities
=============

Entities for code analysis and management.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel


class Repository(BaseModel):
    """Repository containing code files."""
    
    repository_id: UUID
    name: str
    url: Optional[str] = None
    created_at: datetime
    metadata: Dict[str, Any] = {}


class File(BaseModel):
    """A file within a repository."""
    
    file_id: UUID
    repository_id: UUID
    path: str
    content: str
    language: str
    created_at: datetime
    metadata: Dict[str, Any] = {}


class Symbol(BaseModel):
    """A symbol (function, class, etc.) within a file."""
    
    symbol_id: UUID
    file_id: UUID
    name: str
    symbol_type: str  # e.g., "function", "class", "method"
    start_line: int
    end_line: int
    created_at: datetime
    metadata: Dict[str, Any] = {}


class Dependency(BaseModel):
    """A dependency of a file or symbol."""
    
    dependency_id: UUID
    source_id: UUID
    name: str
    version: str
    type: str  # e.g., "package", "module"
    created_at: datetime
    metadata: Dict[str, Any] = {}


class Reference(BaseModel):
    """A reference to another symbol or file."""
    
    reference_id: UUID
    source_id: UUID
    from_symbol_id: Optional[UUID] = None
    to_symbol_id: Optional[UUID] = None
    file_id: Optional[UUID] = None
    reference_type: str  # e.g., "import", "call", "inheritance"
    created_at: datetime
    metadata: Dict[str, Any] = {}