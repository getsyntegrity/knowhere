"""
FileAdapter implementation for the canonical knowledge model.

This adapter converts provider-specific file representations into canonical File entities.
"""

from typing import List, Any
from hashlib import sha256
import os

from canonical.contracts.file_adapter import FileAdapterContract
from canonical.entities.file import File
from canonical.factory import CanonicalFactory


class FileAdapter(FileAdapterContract):
    """
    Converts provider-specific file data into canonical File entities.
    
    This implementation follows the FileAdapter contract requirements:
    - Derives deterministic id from file's path and repository origin
    - Computes content checksum using SHA-256
    - Extracts or infers language from available metadata
    - Populates path as relative path within repository
    - Does not populate symbols, chunks, or references (handled by other adapters)
    """
    
    def __init__(self, factory: CanonicalFactory):
        """
        Initialize the FileAdapter with a CanonicalFactory.
        
        Args:
            factory: CanonicalFactory instance for creating canonical entities
        """
        self.factory = factory
    
    def convert(self, provider_file_data: Any) -> List[File]:
        """
        Convert provider-specific file data into canonical File entities.
        
        Args:
            provider_file_data: Provider-specific file data
            
        Returns:
            List[File]: One or more canonical File entities
            
        Raises:
            ValueError: If the input data cannot be converted to canonical File entities
        """
        # Handle different types of provider file data
        if hasattr(provider_file_data, 'path') and hasattr(provider_file_data, 'content'):
            # This appears to be a file-like object with path and content
            return [self._convert_file_object(provider_file_data)]
        elif isinstance(provider_file_data, dict):
            # This appears to be a dictionary with file data
            return [self._convert_file_dict(provider_file_data)]
        else:
            # Try to handle as a generic object
            return [self._convert_generic_file(provider_file_data)]
    
    def _convert_file_object(self, file_obj: Any) -> File:
        """Convert a file object with path and content attributes."""
        # Extract path and content
        path = getattr(file_obj, 'path', '')
        content = getattr(file_obj, 'content', '')
        
        # Extract repository_id from file object if available
        repository_id = getattr(file_obj, 'repository_id', None)
        
        # Compute checksum and size_bytes
        content_bytes = content.encode('utf-8') if isinstance(content, str) else content
        checksum = sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)
        
        # Determine language
        language = self._infer_language(path)
        
        # Create file entity using build_file
        file_entity = self.factory.build_file(
            repository_id=repository_id,
            path=path,
            checksum=checksum,
            size_bytes=size_bytes,
            language=language,
        )
        
        return file_entity
    
    def _convert_file_dict(self, file_dict: dict) -> File:
        """Convert a dictionary containing file data."""
        # Extract required fields
        path = file_dict.get('path', '')
        content = file_dict.get('content', '')
        repository_id = file_dict.get('repository_id')
        
        # Compute checksum and size_bytes
        content_bytes = content.encode('utf-8') if isinstance(content, str) else content
        checksum = sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)
        
        # Determine language
        language = file_dict.get('language', self._infer_language(path))
        
        # Create file entity using build_file
        file_entity = self.factory.build_file(
            repository_id=repository_id,
            path=path,
            checksum=checksum,
            size_bytes=size_bytes,
            language=language,
        )
        
        return file_entity
    
    def _convert_generic_file(self, file_data: Any) -> File:
        """Convert generic file data."""
        # Try to extract path and content from the object
        path = getattr(file_data, 'path', str(file_data))
        content = getattr(file_data, 'content', '')
        
        # Extract repository_id if available
        repository_id = getattr(file_data, 'repository_id', None)
        
        # Compute checksum and size_bytes
        content_bytes = content.encode('utf-8') if isinstance(content, str) else content
        checksum = sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)
        
        # Determine language
        language = self._infer_language(path)
        
        # Create file entity using build_file
        file_entity = self.factory.build_file(
            repository_id=repository_id,
            path=path,
            checksum=checksum,
            size_bytes=size_bytes,
            language=language,
        )
        
        return file_entity
    
    def _infer_language(self, path: str) -> str:
        """
        Infer programming language from file path.
        
        Args:
            path: File path
            
        Returns:
            Language identifier or 'unknown'
        """
        if not path:
            return 'unknown'
        
        # Map file extensions to languages
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.cs': 'csharp',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.sh': 'shell',
            '.pl': 'perl',
            '.sql': 'sql',
            '.html': 'html',
            '.css': 'css',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.md': 'markdown',
        }
        
        # Get extension
        _, ext = os.path.splitext(path)
        return language_map.get(ext.lower(), 'unknown')
