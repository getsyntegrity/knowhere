# Knowhere MCP Server

> Parse documents into structured, RAG-ready data through [MCP](https://modelcontextprotocol.io/) — one tool call, zero integration friction.

Wraps the [Knowhere API](https://knowhereto.ai) so any MCP-compatible AI agent (Claude, Cursor, OpenAI Agents SDK, etc.) can parse PDFs, DOCX, XLSX, PPTX and more.

## Quick Start

### 1. Install

```bash
cd knowhere-mcp
pip install -e .
```

### 2. Set your API key

```bash
export KNOWHERE_API_KEY="sk_live_..."
```

Get your key at [knowhereto.ai/login](https://knowhereto.ai/login).

### 3. Test interactively

```bash
fastmcp dev server.py
```

This opens a web UI where you can test each tool.

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

Restart Claude Desktop. You'll see a 🔨 icon showing Knowhere tools are available.

## Connect to Cursor

Add to `.cursor/mcp.json` in your project:

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

## Available Tools

| Tool | Description |
|------|-------------|
| `parse_document` | Submit a URL → auto-wait → return structured chunks |
| `get_job_status` | Check status of a running job |
| `get_parsed_chunks` | Download & extract chunks from a completed job |

### Example: Parse a PDF

```
Agent: "Parse this paper: https://arxiv.org/pdf/1706.03762.pdf"

→ Knowhere MCP tool call: parse_document(source_url="https://arxiv.org/pdf/1706.03762.pdf")

→ Returns: 42 structured chunks with headings, tables, formulas, and metadata
```

## Pricing

Knowhere API uses pay-as-you-go pricing: **$1.50 per 1,000 pages**. [Details →](https://knowhereto.ai/#pricing)

## Links

- [Knowhere API Docs](https://docs.knowhereto.ai/)
- [Get API Key](https://knowhereto.ai/login)
- [MCP Protocol](https://modelcontextprotocol.io/)
