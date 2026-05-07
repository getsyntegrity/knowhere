<img width="1000" height="233" alt="20260506-102713" src="https://github.com/user-attachments/assets/896e64d2-e50e-4158-b71c-bc69e11c7c65" />

<h1 align="center">Prepare unstructured data for AI Agents</h1>

<p align="center">
  <a href="https://www.python.org/downloads/">
    <img alt="Python Version" src="https://img.shields.io/badge/Python-%3E%3D%203.11-3776AB.svg?style=for-the-badge&logo=python&logoColor=white&labelColor=000000">
  </a>
  <a href="https://github.com/Ontos-AI/knowhere/stargazers">
    <img alt="GitHub stars" src="https://img.shields.io/github/stars/ontos-ai/knowhere?style=for-the-badge&logo=github&labelColor=000000">
  </a>
  <a href="https://github.com/Ontos-AI/knowhere/actions">
    <img alt="Build Status" src="https://img.shields.io/github/actions/workflow/status/Ontos-AI/knowhere/pr-ci.yml?style=for-the-badge&labelColor=000000">
  </a>
  <br>
  <a href="https://github.com/Ontos-AI/knowhere/discussions">
    <img alt="Join the community on GitHub" src="https://img.shields.io/badge/Join%20the%20community-blueviolet.svg?style=for-the-badge&logo=GitHub&labelColor=000000&logoWidth=20">
  </a>
  <a href="https://ghcr.io/ontos-ai/knowhere">
    <img alt="Container Images" src="https://img.shields.io/badge/CONTAINER%20IMAGES-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white&labelColor=000000">
  </a>
  <a href="https://github.com/Ontos-AI/knowhere/blob/main/LICENSE">
    <img alt="License: Apache 2.0" src="https://img.shields.io/badge/APACHE%202.0-D97706.svg?style=for-the-badge&label=LICENSE&labelColor=000000">
  </a>
</p>

<p align="center">
  🔗 <a href="https://knowhereto.ai">Website</a> |
  📄 <a href="https://docs.knowhereto.ai/">Docs</a> |
  🏠 <a href="https://github.com/Ontos-AI/knowhere-self-hosted">Self-Host</a>
</p>

Knowhere is the open-source infrastructure for unstructured data processing. It automates the complex pipeline of extracting, parsing, and transforming messy documents into structured, high-quality data optimized for *AI Agents*, *Agentic RAG*, and *traditional vector-based RAG workflows*.

> [!NOTE]
> **Get started in seconds with Knowhere Cloud.**
> Avoid the complexity of self-deployment. Use our managed API at [knowhereto.ai](https://knowhereto.ai) and enjoy **$5 in free credits** upon registration.

## 📢 News

- **May 7, 2026**: 🚀 **Knowhere is now Open Source!** We have open-sourced our entire stack for document ingestion, parsing, and agentic RAG. You can now self-host the full platform using [knowhere-self-hosted](https://github.com/Ontos-AI/knowhere-self-hosted). Check out our [Contribution Guide](CONTRIBUTING.md) to get involved!
- **Apr 30, 2026**: 📦 **Version [2026.04.30.1](https://github.com/Ontos-AI/knowhere/releases/tag/2026.04.30.1) has been released.** This update includes several stability improvements and initial support for the agentic RAG layer. See the [full changelog](https://github.com/Ontos-AI/knowhere/commits/2026.04.30.1) for details.

## How it Works

Knowhere has one simple goal: turn uploaded documents into a long-term memory store that agents can understand, navigate, and cite.

The system can be understood as a three-stage pipeline:

```text
Document parsing -> Memory graph construction -> Agentic retrieval -> Cited results
```

### 1. Document Parsing

Knowhere first profiles each uploaded file and routes it to the right parser: regular PDF, scanned drawing, Word, PowerPoint, spreadsheet, image, Markdown, or plain text. The parser converts the original file into structured content units:

- `text`: paragraphs, headings, and body content
- `table`: table content and table asset references
- `image`: image content, OCR, or visual summaries
- `path`: the hierarchical location of each chunk in the source document
- `metadata`: summaries, keywords, media references, and contextual links between knowledge chunks and documents of various formats

The parser is designed to preserve document structure, not just extract raw text. Heading hierarchy, section paths, images, and tables are converted into chunks that can be searched, navigated, and cited.

### 2. Memory Graph Construction

After parsing, Knowhere publishes the chunks into a canonical retrieval state:

- `Document` represents a user document.
- `DocumentSection` stores the document's section hierarchy.
- `DocumentChunk` stores the final content units returned to users or agents.
- `GraphNode` stores document-level memory, including summaries, keywords, chunk counts, media types, and navigation sections.
- `GraphEdge` stores relationships between documents.

The graph is intentionally lightweight. Its purpose is not to create an overly complex ontology, but to help the system understand which documents may be related, what each document is about, and why neighboring documents might matter. The current graph centers on document-level nodes and builds connections from keyword overlap, summaries, and navigation structure, making it useful for fast routing and expansion during retrieval.

### 3. Agentic Retrieval

At query time, Knowhere combines bottom-layer retrieval with agent-guided navigation:

- **Bottom discovery**: retrieve candidate chunks from path, content, and term channels, then fuse them with RRF.
- **Document selection**: the agent reads the memory graph overview and selects potentially relevant documents.
- **Path selection**: the agent reviews compact chunk previews and selects the most relevant section or chunk paths.
- **Hierarchical navigation**: for large documents, the agent takes a progressive strategy; it first inspects top-level and second-level sections, then expands selected sections to leaf chunks.
- **Result merging**: agent-selected paths and bottom-layer candidates are merged, deduplicated, ranked, and returned with source citations.

This gives Knowhere the stability of traditional retrieval and the structural awareness of agent navigation. The final output is not just a text snippet. It is cited evidence: the source document, section, chunk, and, when needed, linked image or table assets.

> **TL;DR**: Knowhere parses documents into structured memory units, organizes them with a lightweight graph, and lets agents navigate through graph context and section paths to find evidence that can be reliably cited.

## Features

- **Multi-modal Parsing**: High-fidelity extraction from PDF, Office, and images, preserving headings, tables, and hierarchical paths.
- **Lightweight Memory Graph**: Context-aware organization that links documents and chunks for better relationship understanding.
- **Agentic RAG**: A hybrid retrieval engine combining traditional search (RRF) with autonomous agent navigation.
- **Evidence-based Citations**: Every result is backed by traceable source paths, ensuring reliability for AI Agent decision-making.

## Repository Layout

```text
knowhere-api/
├── apps/
│   ├── api/
│   └── worker/
├── packages/
│   └── shared-python/
├── deploy/
│   ├── docker/
│   └── local-dev/
└── .github/workflows/
    └── build-images.yml
```

## Prerequisites

- Python 3.11+
- `uv`
- Docker with `docker compose`
- a local Chrome or Chromium driver if you plan to run document layout parsing
  flows

## Quick Start

1. Sync the workspace dependencies:

```bash
uv sync --all-packages
```

2. Copy the environment examples:

```bash
cp apps/api/.env.example apps/api/.env
cp apps/worker/.env.example apps/worker/.env
```

3. Update the copied `.env` files with the values you need for local work:

- database and Redis connection settings
- S3-compatible storage credentials
- `SECRET_KEY`
- `USERS_DATA_PATH`
- `DS_KEY`
- any optional LLM, billing, or webhook providers you want to enable

The example files default to the open-source/self-hosted behavior:

- `API_STANDALONE_MODE_ENABLED=false` for the combined dashboard + API flow, where
  the dashboard initializes Better Auth tables before API migrations.
- `BILLING_ENABLED=false`, so Stripe and credit deduction are not required.
- `RATE_LIMIT_ENABLED=false` for local/self-hosted convenience; set it to
  `true` when you want API rate limits enforced.

For API-only development without the dashboard, set `API_STANDALONE_MODE_ENABLED=true`,
run API migrations, then create an API-only user/key:

```bash
cd apps/api
uv run --python 3.11 python -m alembic upgrade heads
uv run --python 3.11 python scripts/init_user.py --email you@example.com
```

If you plan to use the dashboard, start the combined self-hosted stack and
register through the dashboard instead of using `scripts/init_user.py`.

4. Start the local infrastructure stack:

```bash
./deploy/local-dev/start-dev.sh
```

If you also want the helper to initialize the local API user state, rerun it
with `--init-user`:

```bash
./deploy/local-dev/start-dev.sh --init-user
```

5. Start the API and worker in separate terminals:

```bash
cd apps/api && uv run main.py
cd apps/worker && uv run worker.py
```

## Quality Checks

Run lint checks from the repository root:

```bash
make lint
```

Apply safe Ruff fixes:

```bash
make lint-fix
```

Run type checks across the API, worker, and shared source code:

```bash
make typecheck
```

Run both lint and type checks:

```bash
make check
```

## Local Endpoints

- API: `http://localhost:5005`
- OpenAPI docs: `http://localhost:5005/docs`
- LocalStack: `http://localhost:4566`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Additional Guides

- External dependency guide:
  [docs/external-services.md](docs/external-services.md)

## Project Governance

- Licensed under Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
- Contribution workflow and branch expectations live in
  [CONTRIBUTING.md](CONTRIBUTING.md).
- Security reporting guidance lives in [SECURITY.md](SECURITY.md).
- Community behavior expectations live in
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
