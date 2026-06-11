# Knowhere Core

Core architecture for Knowhere - foundation layer with abstract provider interfaces.

## Overview

This package provides the foundational architecture for Knowhere, including:

- Abstract provider interfaces for all major components
- Core entity definitions
- Type system and enums
- Domain exceptions

## Package Structure

```
knowhere/
├── entities/          # Core data models
├── providers/         # Abstract provider interfaces
├── types/             # Type definitions and enums
└── exceptions/        # Custom exceptions
```

## Core Entities

- `KnowledgeSource`: Root entity for all ingested knowledge origins
- `KnowledgeChunk`: Atomic retrieval unit across all layers
- `KnowledgeVersion`: Versioned snapshot of a KnowledgeSource
- `RetrievalPipeline`: Defines retrieval strategy for a KnowledgeSource
- `GraphNode`/`GraphEdge`: Graph representation of knowledge relationships
- `Memory`/`MemoryFact`/`MemoryRelationship`/`MemorySummary`: Memory management entities
- `Repository`/`File`/`Symbol`/`Dependency`/`Reference`: Code analysis entities

## Provider Interfaces

- `StorageProvider`: Storage operations
- `VectorProvider`: Vector storage operations
- `EmbeddingProvider`: Text embedding generation
- `GraphProvider`: Graph storage operations
- `CodeParserProvider`: Code parsing operations
- `RankingStrategy`: Chunk ranking strategies
- `CompressionProvider`: Chunk compression operations
- `ContextBuilder`: Context building operations

## Installation

```bash
pip install knowhere-core
```

## Usage

```python
from knowhere import KnowledgeSource, KnowledgeChunk, StorageProvider

# Create a knowledge source
source = KnowledgeSource(
    source_id="123e4567-e89b-12d3-a456-426614174000",
    source_type="github",
    ingestion_timestamp="2023-01-01T00:00:00Z",
    hash="abc123",
    status="active",
    metadata={}
)

# Create a knowledge chunk
chunk = KnowledgeChunk(
    chunk_id="chunk123",
    source_id="123e4567-e89b-12d3-a456-426614174000",
    knowledge_version="123e4567-e89b-12d3-a456-426614174001",
    chunk_type="CODE_FILE",
    content="print('Hello, World!')",
    created_at="2023-01-01T00:00:00Z"
)
```

## Development

To contribute to this package:

1. Install dependencies:
   ```bash
   pip install -e .
   ```

2. Run tests:
   ```bash
   pytest tests/
   ```

3. Run linter:
   ```bash
   ruff check .
   ```

4. Run type checker:
   ```bash
   pyright .
   ```