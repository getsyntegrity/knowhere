# CodeParserProvider Contract

**Layer**: Code Memory Layer | **Spec**: [FR-004, FR-017](../spec.md) | **Date**: 2026-06-11

## Purpose

Language-specific parsing of source code into symbols, dependencies, and references.

## Interface

```python
class CodeParserProvider:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]
    supported_languages: list[str]  # e.g., ["python", "typescript", "rust"]

    def parse_file(self, path: str, language: str, content: str) -> ParseResult:
        """
        Parse a source file into symbols, dependencies, and references.
        
        Args:
            path: File path relative to repository root
            language: Programming language identifier
            content: Raw file content
            
        Returns:
            ParseResult with lists of Symbol, Dependency, Reference objects.
            
        Raises:
            UnsupportedLanguageError: Language not supported by this provider
            ParseError: File could not be parsed
        """
```

## Contract Tests

- `test_parse_file_returns_symbols`
- `test_parse_file_returns_dependencies`
- `test_parse_file_returns_references`
- `test_unsupported_language_raises_error`
- `test_provider_metadata`
- `test_supported_languages_list`
