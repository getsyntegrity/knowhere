# Quickstart: KNOW-001 Foundation Architecture

**Date**: 2026-06-11 | **Plan**: [plan.md](./plan.md)

## Prerequisites

- Python 3.11+
- Existing knowhere dev environment setup (`uv sync --all-packages`)
- PostgreSQL + Qdrant running (via `./deploy/local-dev/start-dev.sh`)

## Running with In-Memory Mock Stack (No External Services)

For development and testing without external dependencies:

```bash
# Run just the in-memory retrieval pipeline
python -m shared.services.retrieval.pipeline_demo
```

## Implementing a New Provider

1. Create a new class inheriting from the abstract provider interface:

```python
from shared.services.ingestion.source_provider import SourceProvider
from shared.models.schemas.knowledge_chunk import KnowledgeChunk

class MyCustomSourceProvider(SourceProvider):
    provider_name = "my-custom-source"
    provider_version = "0.1.0"
    provider_capabilities = [
        {"name": "custom-source-ingestion", "version": "0.1.0", "stability": "beta"}
    ]

    def ingest(self, config):
        # Implement source-specific ingestion logic
        # Return list of KnowledgeChunk objects
        return [...]
```

2. Register the provider in configuration:

```yaml
# config/providers.yml
source:
  my-custom:
    provider: "my_custom_module.MyCustomSourceProvider"
    config:
      # Provider-specific config
      pass
```

3. Run contract tests:

```bash
pytest tests/contract/providers/test_source_provider.py
```

## Running Contract Tests

```bash
# All provider contract tests
pytest tests/contract/providers/

# Single provider interface
pytest tests/contract/providers/test_vector_provider.py
```

## Running the Full Pipeline (Demo)

```bash
# 1. Start services (PostgreSQL + Redis + Qdrant)
./deploy/local-dev/start-dev.sh

# 2. Ingest a document
curl -X POST http://localhost:5005/v1/ingestion/start \
  -H "Content-Type: application/json" \
  -d '{"source_type": "document", "path": "/path/to/file.pdf"}'

# 3. Run a retrieval query
curl -X POST http://localhost:5005/v1/retrieval/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the architecture?", "top_k": 10}'

# 4. Check retrieval pipeline configuration
curl http://localhost:5005/v1/retrieval/pipelines
```

## Verifying Determinism

```bash
# Run same query twice against same knowledge version
QUERY='{"query": "test query", "knowledge_version": "v1"}'

curl -s -X POST http://localhost:5005/v1/retrieval/query \
  -H "Content-Type: application/json" \
  -d "$QUERY" > result1.json

curl -s -X POST http://localhost:5005/v1/retrieval/query \
  -H "Content-Type: application/json" \
  -d "$QUERY" > result2.json

# Verify deterministically equivalent
python -c "
import json
r1 = json.load(open('result1.json'))
r2 = json.load(open('result2.json'))
print('Equivalent:', r1 == r2)
"
```

## Implementing Contract Tests

Each provider interface has a contract test suite. To add tests for a new implementation:

```python
# tests/contract/providers/test_my_vector_provider.py
import pytest
from shared.services.retrieval.vector_provider import VectorProvider

class TestVectorProviderContract:
    @pytest.fixture
    def provider(self):
        return MyVectorProvider()  # Your implementation

    def test_upsert_and_search(self, provider):
        chunks = [create_test_chunk("hello world")]
        provider.upsert(chunks)
        results = provider.search("hello", top_k=5)
        assert len(results) > 0
        assert results[0].chunk_id == chunks[0].chunk_id
```

## Project Structure (Key Paths)

```text
packages/shared-python/shared/
├── models/
│   ├── database/     # SQLAlchemy ORM models
│   └── schemas/      # Pydantic schemas
├── services/
│   ├── ingestion/    # Ingestion Layer
│   ├── knowledge_graph/  # Knowledge Graph Layer
│   ├── retrieval/    # Retrieval Pipeline + Ranking
│   │   ├── ranking/
│   │   ├── compression/
│   │   └── context_builder/
│   └── providers/    # Provider registry + versioning
└── utils/
```

## Common Commands

```bash
uv sync --all-packages         # Install all dependencies
pytest tests/unit/             # Run unit tests
pytest tests/contract/         # Run contract tests  
pytest tests/integration/      # Run integration tests
make lint                      # Ruff lint
make typecheck                 # Pyright
