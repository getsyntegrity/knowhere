---
name: knowhere_memory
description: Auto-discover and search knowledge from Knowhere parsed documents. Use when the user asks questions, needs information, or references their knowledge base.
---

# Knowhere Knowledge Memory

This agent has access to a **personal knowledge base** managed by Knowhere.

## When to Use

Activate this skill when:
- The user asks a question that might be answered by their documents
- The user says "查一下", "帮我找", "我的资料里有没有", "知识库" etc.
- The user needs context from their uploaded/parsed documents
- The user asks "我有什么资料" or wants an overview of their knowledge base

## How to Access Knowledge

### Option 1: MCP Tools (Preferred)

If you have `knowhere` MCP tools available, use them directly:

- **`search_knowledge(query, top_k=5)`** — Search for relevant document chunks
- **`get_knowledge_overview()`** — Get a file-level overview with keywords and connections

### Option 2: Direct File Access (Fallback)

If MCP is not configured, read files directly from:

```
~/.knowhere/
└── {kb_id}/
    ├── knowledge_graph.json       ← Read this first for file-level overview
    ├── chunk_stats.json           ← Hit counts and usage data per chunk
    └── {document_name}/           ← Per-document subdirectory
        ├── chunks.json            ← Full chunk data for this document
        ├── hierarchy.json         ← Document structure hierarchy
        └── images/tables/...      ← Embedded media
```

**Steps:**
1. Read `~/.knowhere/{kb_id}/knowledge_graph.json`
2. Check `files` dict for document list with `chunks_count`, `types`, `top_keywords`, `importance`
3. Check `edges` for cross-file relationships (shows `top_connections` with chunk names)
4. To get detailed content, read `~/.knowhere/{kb_id}/{document_name}/chunks.json`

## Response Style

When returning knowledge search results:
- Cite the source document path
- Include relevant keywords
- Mention related chunks if the graph shows connections
- Be transparent about whether information is from parsed documents vs. general knowledge
