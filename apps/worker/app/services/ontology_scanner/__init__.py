"""
Ontology Scanner Service
Scans local filesystem to discover user knowledge assets, score them,
and produce a structured ontology + parse queue for cold-start RAG.
"""
from .scanner import FileSystemScanner, quick_scan

__all__ = ["FileSystemScanner", "quick_scan"]
