"""
ChunkType Enum
==============

Enumeration of all possible chunk types in the Knowhere system.
"""

from enum import Enum


class ChunkType(Enum):
    """Enumeration of all possible chunk types."""
    
    # Code-related chunks
    CODE_FILE = "CODE_FILE"
    CODE_CLASS = "CODE_CLASS"
    CODE_FUNCTION = "CODE_FUNCTION"
    CODE_INTERFACE = "CODE_INTERFACE"
    CODE_SYMBOL = "CODE_SYMBOL"
    
    # Document-related chunks
    DOCUMENT = "DOCUMENT"
    DOCUMENT_SECTION = "DOCUMENT_SECTION"
    DOCUMENT_PARAGRAPH = "DOCUMENT_PARAGRAPH"
    
    # Memory-related chunks
    MEMORY = "MEMORY"
    MEMORY_FACT = "MEMORY_FACT"
    MEMORY_SUMMARY = "MEMORY_SUMMARY"
    
    # Other data types
    DATASET = "DATASET"
    IMAGE = "IMAGE"
    
    # Custom and unknown types
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"