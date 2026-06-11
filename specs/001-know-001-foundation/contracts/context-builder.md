# ContextBuilder Contract

**Layer**: Context Builder Layer | **Spec**: [FR-011, FR-021](../spec.md) | **Date**: 2026-06-11

## Interface

```python
class ContextBuilder:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    def build(self, chunks: list[CompressedChunk], token_budget: int, query: str) -> Context:
        """
        Assemble final prompt-ready context from compressed chunks.
        
        Responsibilities:
        - Order chunks by relevance
        - Prioritize critical content (high score chunks first)
        - Deduplicate overlapping passages
        - Enforce token budget constraints
        
        Args:
            chunks: Compressed result chunks
            token_budget: Maximum tokens for final context
            query: Original query
            
        Returns:
            Context object with ordered, deduplicated, budgeted content.
            
        Raises:
            BudgetTooSmallError: Token budget is below minimum output floor
        """
```

## Contract Tests

- `test_build_respects_token_budget`
- `test_build_deduplicates_overlapping_chunks`
- `test_build_orders_by_relevance`
- `test_budget_too_small_reports_warning`
