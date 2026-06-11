# CompressionProvider Contract

**Layer**: Compression Layer | **Spec**: [FR-037–FR-045](../spec.md) | **Date**: 2026-06-11

## Interface

```python
class CompressionProvider:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    def compress(self, candidates: list[RankedResult], token_budget: int, query: str) -> list[CompressedChunk]:
        """
        Compress ranked candidates to fit within token budget.
        
        Args:
            candidates: Ranked results from Ranking Layer
            token_budget: Maximum tokens for compressed output
            query: Original query (for relevance-aware compression)
            
        Returns:
            List of compressed chunks within token budget.
        """

    def estimate_ratio(self, candidates: list[RankedResult]) -> float:
        """Estimate expected compression ratio without executing."""
```

## Quality Metrics

Compression quality is measured by:
- **Recall**: fraction of relevant info preserved (benchmark suite)
- **Precision**: fraction of compressed output relevant to query
- **Faithfulness**: no hallucinated information in compressed output

## Contract Tests

- `test_compress_respects_token_budget`
- `test_compress_returns_non_empty`
- `test_compress_preserves_critical_content`
- `test_estimate_ratio_within_reasonable_range`
