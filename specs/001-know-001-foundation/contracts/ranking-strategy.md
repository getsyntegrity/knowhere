# RankingStrategy Contract

**Layer**: Ranking Layer | **Spec**: [FR-019, FR-011](../spec.md) | **Date**: 2026-06-11

## Interface

```python
class RankingStrategy:
    provider_name: str
    provider_version: str
    provider_capabilities: list[Capability]

    def rank(self, candidates: list[ChunkResult], query: str, weights: dict = None) -> list[RankedResult]:
        """
        Rank candidates by relevance to the query.
        
        Args:
            candidates: Retrieved chunk results from one or more strategies
            query: Original user query
            weights: Optional per-strategy weights (for fusion strategies)
            
        Returns:
            Ranked list of results with scores and optional explanations.
        """
```

## Contract Tests

- `test_rank_returns_sorted_results`
- `test_rank_top_result_most_relevant`
- `test_same_query_same_data_returns_same_order`
