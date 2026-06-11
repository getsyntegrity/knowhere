"""
Exceptions
==========

Custom exceptions for the Knowhere system.
"""

from typing import Optional


class ProviderNotFoundError(Exception):
    """Raised when a requested provider is not found."""
    
    def __init__(self, provider_name: str, message: Optional[str] = None):
        self.provider_name = provider_name
        self.message = message or f"Provider '{provider_name}' not found"
        super().__init__(self.message)


class VersionCorruptedError(Exception):
    """Raised when a knowledge version is corrupted."""
    
    def __init__(self, version_id: str, message: Optional[str] = None):
        self.version_id = version_id
        self.message = message or f"Knowledge version '{version_id}' is corrupted"
        super().__init__(self.message)


class ConfigurationError(Exception):
    """Raised when there's a configuration issue."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ChunkValidationError(Exception):
    """Raised when a chunk fails validation."""
    
    def __init__(self, chunk_id: str, message: str):
        self.chunk_id = chunk_id
        self.message = message
        super().__init__(f"Chunk '{chunk_id}' validation failed: {message}")