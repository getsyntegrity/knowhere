# EmbeddingProvider Contract

**Layer**: Core | **Spec**: [FR-018, FR-031](../spec.md) | **Date**: 2026-06-11

## Interface

```python
class EmbeddingProvider:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]
    embedding_dimensions: int  # Output vector dimensionality

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Convert text strings to embedding vectors.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (one per input text).
            
        Raises:
            EmbeddingError: Model unavailable or rate limited
        """

    def embed_single(self, text: str) -> list[float]:
        """Convenience: embed a single text string."""
```

## Fallback

SHOULD configure fallback chain (primary → secondary) for high availability.

## Contract Tests

- `test_embed_returns_correct_dimensionality`
- `test_embed_batch_returns_one_vector_per_input`
- `test_embed_similar_texts_have_similar_vectors`
- `test_provider_metadata`
