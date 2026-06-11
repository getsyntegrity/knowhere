"""
Metrics Types
=============

Data structures for provider capabilities and quality metrics.
"""

from typing import List, Optional
from pydantic import BaseModel


class Capability(BaseModel):
    """Represents a provider capability with name, version, and stability."""
    
    name: str
    version: str
    stability: str  # e.g., "stable", "beta", "alpha"


class MetricReport(BaseModel):
    """Base class for metric reports."""
    
    pass


class ConsistencyReport(BaseModel):
    """Report for consistency checks."""
    
    is_consistent: bool
    details: Optional[str] = None
    errors: List[str] = []