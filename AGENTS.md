# Repository Instructions

## Branch Naming

Codex agents and contributors must create branches with this format:

```text
<type>/<user>/<description>
```

- `type` should be lowercase and should normally be one of:
  `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `perf`, `ci`, `build`,
  or `revert`.
- `user` should identify the human owner of the work, usually their GitHub
  username. Do not use a generic tool name such as `codex`.
- `description` should be short, lowercase, and kebab-case.

Examples:

```text
feat/alice/add-document-preview
fix/bob/chunk-position-range
refactor/chris/extract-chunk-converter
```

## Project Structure

```text
knowhereapi-main/
├── apps/
│   ├── api/          # FastAPI REST API (port 5005)
│   │   ├── app/
│   │   │   ├── api/v1/routes/   # Endpoint handlers
│   │   │   ├── services/        # Business logic (auth, ingestion, billing)
│   │   │   └── repositories/    # Data access layer
│   │   └── main.py              # Entrypoint, runs migrations on start
│   ├── worker/       # Celery worker for async document processing
│   │   ├── app/
│   │   │   ├── services/document_parser/  # All parser modules
│   │   │   └── services/workload/         # Celery task handlers
│   │   └── worker.py                      # Celery entrypoint
│   ├── web/          # Frontend (separate repo: knowhere-dashboard)
│   └── docs/         # Internal documentation
├── packages/
│   └── shared-python/shared/    # Shared library (pip: knowhere-shared)
│       ├── models/database/     # SQLAlchemy ORM models
│       ├── models/schemas/      # Pydantic request/response schemas
│       ├── services/retrieval/  # Core retrieval engine
│       ├── services/chunks/     # DataFrame → ChunkPayload conversion
│       ├── services/ai/         # LLM prompt service & AI client
│       ├── services/http/       # Public URL validation and outbound HTTP
│       ├── services/redis/      # Redis state, key language, and retry policy
│       ├── services/quota/      # Shared token-pool quota primitives
│       └── utils/               # Generic text, chunk, and API helpers
└── deploy/                      # Docker Compose & deployment scripts
```

> **SDKs live in standalone repos:**
> - Python SDK → [`Ontos-AI/knowhere-python-sdk`](https://github.com/Ontos-AI/knowhere-python-sdk)
> - Node SDK → [`Ontos-AI/knowhere-node-sdk`](https://github.com/Ontos-AI/knowhere-node-sdk)

## Development Setup

### Prerequisites

- Python 3.11+
- uv (Python package manager)
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 6+

### Local Development

1. Install dependencies:
   ```bash
   uv sync --all-packages
   ```

2. Copy environment files:
   ```bash
   cp apps/api/.env.example apps/api/.env
   cp apps/worker/.env.example apps/worker/.env
   ```

3. Start services:
   ```bash
   ./deploy/local-dev/start-dev.sh
   ```

4. Run the API:
   ```bash
   cd apps/api && uv run main.py
   ```

5. Run the worker:
   ```bash
   cd apps/worker && uv run worker.py
   ```

## Development Workflows

### Running Tests

```bash
make test
```

### Linting and Type Checking

```bash
make lint
make typecheck
```

### Development Commands

```bash
make check         # Run lint + typecheck
make test-coverage # Run tests with coverage
```

## API Service

### Entry Point

`apps/api/main.py` - FastAPI application with Alembic migrations on startup.

### Key Components

- **Routes**: `apps/api/app/api/v1/routes/`
- **Services**: `apps/api/app/services/`
- **Repositories**: `apps/api/app/repositories/`

### Startup Process

1. Loads configuration from `.env`
2. Runs database migrations using Alembic
3. Starts FastAPI server on port 5005

## Worker Service

### Entry Point

`apps/worker/worker.py` - Celery worker with gevent monkey patching.

### Key Components

- **Document Parsers**: `apps/worker/app/services/document_parser/`
- **Workload Handlers**: `apps/worker/app/services/workload/`

### Startup Process

1. Applies gevent monkey patching
2. Patches psycopg2 for cooperative DB access
3. Initializes worker heartbeat
4. Starts Celery worker with Beat subprocess
5. Registers task modules

## Shared Package

### Location

`packages/shared-python/shared/`

### Key Components

- **Database Models**: `models/database/`
- **Pydantic Schemas**: `models/schemas/`
- **Core Services**: `services/`
- **Utilities**: `utils/`

## Configuration

### Settings Structure

All configuration is managed through `shared/core/config/app.py` which combines:
- BaseConfig (environment, logging, security)
- DatabaseConfig (PostgreSQL settings)
- RedisConfig (Redis connection settings)
- CeleryConfig (Celery broker settings)
- AIConfig (LLM settings)
- MineruConfig (MinerU API settings)
- BillingConfig (Billing settings)
- JobConfig (Job processing settings)

### Environment Variables

Environment variables are loaded from `.env` files in each service directory.

## Testing

### Test Structure

- API tests: `apps/api/tests/`
- Worker tests: `apps/worker/tests/`
- Shared package tests: `packages/shared-python/shared/tests/`

### Running Tests

```bash
make test
```

## CI/CD

### CI Workflow

The CI workflow is defined in `.github/workflows/pr-ci.yml` and includes:
- Setting up uv
- Installing dependencies
- Running linting and type checking
- Running tests with coverage
- Building Docker images

### Docker Setup

Docker Compose files are in `deploy/` directory for local development and deployment.

## Key Implementation Patterns

### Deterministic Chunk IDs

`know_id = gen_str_codes(pure_text)` - SHA-based hash of text content only
(excludes image/table asset refs). This enables cross-document dedup:
identical text in different uploads produces the same `chunk_id`.

### Plan-then-Act DOM Mutation

When splitting tables or modifying document structure:
1. **Pass 1 (Investigate)**: Collect mutation targets into a static plan
2. **Pass 2 (Execute)**: Apply mutations in **reverse order** to avoid index shifting

### Image Dedup: Perceptual Hash

`perceptual_hash()` computes a visual fingerprint. Images with identical
hashes are deduplicated within a document, with cached metadata reused.

### Asset Lifecycle (Deterministic UIDs)

`IMAGE_[hash(content+seq)]_IMAGE` - identical images at different positions
receive unique IDs. Context chaining prevention scans backward past binary
identifiers to find the nearest valid text.

### LLM Constraints

- **DeepSeek JSON mode**: Requires the word "json" in the prompt when
  `response_format` is `json_object`
- **Streaming robustness**: Concatenate `delta.content` only if `not None`
- **Token pool rotation**: Ali API keys support per-token RPM limits,
  cooldown, and inline retry with next available token

## Architecture Extension Rules

The KNOW architecture follows an upstream-first model.

If a feature can be implemented through:

- Provider
- Adapter
- Plugin
- Extension Point

it MUST NOT modify upstream core modules.

### Canonical Entities

- KnowledgeSource
- KnowledgeChunk
- KnowledgeVersion
- RetrievalPipeline

### Source of Truth

Storage is authoritative.

VectorStore and GraphStore are derived indices.

Never reconstruct Storage from indices.

### Retrieval Contract

All retrieval operations return KnowledgeChunk references.

Never return provider-specific entities.

### Extension Strategy

New source type:
→ implement SourceProvider

New language:
→ implement CodeParserProvider

New vector backend:
→ implement VectorProvider

New graph backend:
→ implement GraphProvider

New ranking:
→ implement RankingStrategy

New compression:
→ implement CompressionProvider

New context assembly:
→ implement ContextBuilder

## Analytics Tables

#### `retrieval_hit_stats`

Tracks per-chunk and per-document retrieval usage. `hit_count` and `last_hit_at`
feed into `compute_importance_score()` for ranking boost.

#### `retrieval_runs` / `retrieval_steps`

Append-only agentic retrieval analytics. One `retrieval_runs` row per query,
with child `retrieval_steps` rows recording each agent action, its input/output,
latency, and token usage.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:

**Current Plan**: `specs/002-know-002-canonical/plan.md`
<!-- SPECKIT END -->
