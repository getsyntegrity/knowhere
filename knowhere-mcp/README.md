# Knowhere MCP Server

> Parse documents + search your knowledge base through [MCP](https://modelcontextprotocol.io/) — one server, zero integration friction.

A unified MCP server that wraps both the [Knowhere Cloud API](https://knowhereto.ai) and your local knowledge base (`~/.knowhere/`), so AI agents get the complete document intelligence experience.

## Tools

### ☁️ Cloud Tools (require `KNOWHERE_API_KEY`)

| Tool | Description |
|------|-------------|
| `parse_document` | Submit a URL → auto-wait → return structured chunks |
| `get_job_status` | Check status of a running job |
| `get_parsed_chunks` | Download & extract chunks from a completed job |

### 🏠 Local Tools (read `~/.knowhere/`)

| Tool | Description |
|------|-------------|
| `search_knowledge` | Keyword search across all local knowledge bases |
| `get_knowledge_overview` | View KB structure, stats, and cross-file connections |

## Quick Start

### 1. Install

```bash
cd knowhere-mcp
pip install -e .
```

### 2. Set your API key (optional, for cloud tools)

```bash
export KNOWHERE_API_KEY="sk_live_..."
```

Get your key at [knowhereto.ai/login](https://knowhereto.ai/login).

### 3. Test interactively

```bash
fastmcp dev server.py
```

## Connect to Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "knowhere": {
      "command": "python",
      "args": ["/absolute/path/to/knowhere-mcp/server.py"],
      "env": {
        "KNOWHERE_API_KEY": "sk_live_..."
      }
    }
  }
}
```

## Connect to Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "knowhere": {
      "command": "python",
      "args": ["/absolute/path/to/knowhere-mcp/server.py"],
      "env": {
        "KNOWHERE_API_KEY": "sk_live_..."
      }
    }
  }
}
```

## Architecture

```
knowhere-mcp/
├── server.py           ← Unified MCP entry point (5 tools)
├── local_search.py     ← Local KB search + overview logic
├── stats_tracker.py    ← Chunk hit tracking for importance scoring
├── pyproject.toml      ← Package metadata
└── README.md
```

The local search tools track which chunks are accessed and update `~/.knowhere/{kb_id}/chunk_stats.json`. These stats feed into the knowledge graph's file importance calculation on next rebuild, creating a feedback loop: **more searched → higher importance**.

## Pricing

Cloud API is pay-as-you-go: **$1.50 per 1,000 pages**. Local tools are free.

## Links

- [Knowhere API Docs](https://docs.knowhereto.ai/)
- [Get API Key](https://knowhereto.ai/login)
- [MCP Protocol](https://modelcontextprotocol.io/)
