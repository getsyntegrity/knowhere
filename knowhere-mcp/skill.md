---
name: knowhere_memory
description: Auto-discover and search knowledge from Knowhere parsed documents. Use when the user asks questions, needs information, or references their knowledge base.
user-invocable: false
---

# Knowhere Knowledge Memory

This agent has access to a **personal knowledge base** managed by Knowhere.

**Data path**: `~/.knowhere/{kb_id}/` (or `KNOWHERE_HOME` env var)

## When to Use

- User asks a question that might be answered by their documents
- User says "look it up", "search knowledge", "my materials", etc.
- User asks what documents/materials they have

## Retrieval Strategy

### If `search_knowledge` tool is available → Use it (Tier 1)

Call `search_knowledge(query)`. It handles everything internally.

### If no search tool → Self-navigate (Tier 2/3)

#### Tier 2: knowledge_graph.json exists

1. **Read** `~/.knowhere/{kb_id}/knowledge_graph.json`
2. **Match** user query against `files[*].top_keywords` → identify candidate files
3. **Prioritize** by `importance` score
4. **Read** each candidate's `{document_name}/chunks.json` → search `content` and `metadata.keywords`
5. **Expand** via `edges` → check cross-file connections for related chunks

#### Tier 3: No graph, only raw files

1. **List** `~/.knowhere/` directories
2. **Grep** `chunks.json` files for query keywords in `content` field
3. Return matching chunks with `path` and `chunk_id`

## Data Schema

```
~/.knowhere/{kb_id}/
├── knowledge_graph.json          ← Tier 2 entry point
│   { files: { "doc.pdf": { top_keywords, importance, chunks_count } },
│     edges: [{ source, target, top_connections }] }
├── chunk_stats.json              ← Usage tracking
└── {document_name}/
    ├── chunks.json               ← Tier 3 entry point
    │   { chunks: [{ chunk_id, type, path, content, metadata: { summary, keywords } }] }
    ├── hierarchy.json
    ├── images/
    └── tables/
```

## Response Guidelines

- Cite document name + chunk path for each piece of information
- Synthesize from ALL matched files, not just the first hit
- When edges link chunks across files, mention the relationship
- Reply in the user's language
