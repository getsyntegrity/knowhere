"""
KnowledgeVersionStatus Enum
===========================

Enumeration of all possible status states for a KnowledgeVersion.
"""

from enum import Enum


class KnowledgeVersionStatus(Enum):
    """Enumeration of all possible status states for a KnowledgeVersion."""
    
    SEALING = "sealing"
    SEALED = "sealed"
    CORRUPTED = "corrupted"