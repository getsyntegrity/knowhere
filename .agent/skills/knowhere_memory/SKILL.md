---
name: knowhere_memory
description: Auto-discover and search knowledge from Knowhere parsed documents. Use when the user asks questions, needs information, or references their knowledge base.
---

# Knowhere Knowledge Memory

This agent has access to a **personal knowledge base** managed by Knowhere.

## When to Use

Activate this skill when:
- The user asks a question that might be answered by their documents
- The user says "查一下", "帮我找", "知识库", "我的资料" etc.
- The user asks "我有什么资料" or wants an overview

## Data Location

All knowledge data lives under `~/.knowhere/{kb_id}/`:

```
~/.knowhere/
└── {kb_id}/                          # e.g. "chengke_kb"
    ├── knowledge_graph.json          # START HERE — file-level overview + cross-file edges
    ├── chunk_stats.json              # Hit counts / usage stats per chunk
    └── {document_name}/              # One subdir per parsed document
        ├── chunks.json               # All chunks for this document (the actual content)
        ├── hierarchy.json            # Document structure tree
        ├── images/                   # Extracted images (JPEG/PNG)
        └── tables/                   # Extracted tables (HTML files)
```

## File Schema Reference

### knowledge_graph.json — Global Navigation (read this first)

```json
{
  "version": "2.0",
  "stats": {"total_files": 5, "total_chunks": 327, "total_cross_file_edges": 3},
  "files": {
    "报告.docx": {
      "chunks_count": 198,
      "types": {"text": 135, "table": 21, "image": 42},
      "top_keywords": ["基坑", "支护", "施工"],     // TF-IDF top keywords for this file
      "top_summary": "",                             // File-level summary (TBD)
      "importance": 0.85                             // 0-1, based on usage + freshness
    }
  },
  "edges": [
    {
      "source": "file_A.docx", "target": "file_B.pdf",
      "connection_count": 20, "avg_score": 0.95,
      "top_connections": [
        {
          "source_chunk": "第3章 安全措施",           // Human-readable name (path last segment)
          "source_id": "abc123-...",                   // Chunk UUID → use to find in chunks.json
          "target_chunk": "安全管理制度",
          "target_id": "def456-...",
          "relation": "related", "score": 1.0
        }
      ]
    }
  ]
}
```

### chunks.json — Document Content (read per-file, on demand)

Located at `~/.knowhere/{kb_id}/{document_name}/chunks.json`.

```json
{
  "chunks": [
    {
      "chunk_id": "34da946a-5938-578c-...",        // UUID, unique across KB
      "type": "text",                               // "text" | "table" | "image"
      "path": "Default_Root/报告.docx/第一章/1.1",  // Hierarchical path
      "content": "actual content...",                   // Full content of this chunk
      "metadata": {
        "summary": "LLM-generated summary (may be empty)",
        "keywords": ["Extracted keywords"],
        "tokens": ["Jieba tokenization"],
        "length": 1234,
        "page_nums": "Source pages (PDF/DOCX)"
      }
    }
  ]
}
```

**Content format by chunk type:**
- `text`: Plain text with embedded markers like `IMAGE_uuid_IMAGE` or `TABLE_uuid_TABLE`
- `table`: Raw HTML (`<table>...</table>`)
- `image`: Brief description + `IMAGE_uuid_IMAGE` marker; actual image file in `images/` subdir

### hierarchy.json — Document Structure

Three sub-trees:
- `images/`: all extracted images with descriptive names
- `tables/`: all extracted tables with header-based names
- `Default_Root/{filename}/`: section hierarchy (chapters → subsections)

## Retrieval Workflow

All operations below are **read-only** — use your file reading tools (e.g. `view_file`, `read_file`) to read JSON files directly. Do NOT use shell commands like `cat` — use native file reading tools that don't require user approval.

Follow this pattern — do NOT explore the filesystem blindly:

### Step 1: Read knowledge_graph.json (global navigation)

Read the file `~/.knowhere/{kb_id}/knowledge_graph.json` using your file reading tool.

From this you get:
- **File list** with `top_keywords` → match user's question against ALL files, not just one
- **importance** → prioritize high-value files when multiple match
- **edges** → note which matched files connect to other files (you'll need these in Step 3)

**Important**: Identify ALL candidate files whose `top_keywords` are relevant to the query. Do not stop at the first match.

### Step 2: Search ALL candidate files' chunks.json

For EACH candidate file identified in Step 1, read `~/.knowhere/{kb_id}/{document_name}/chunks.json`.

Search the `chunks` array:
- Match `metadata.summary` or `content` against the user's query
- Use `metadata.keywords` for topic matching
- Use `path` to understand where the chunk sits in the document structure
- Use `chunk_id` to cross-reference with edge `source_id`/`target_id`

Collect matching chunks from ALL files, not just the first one that hits.

### Step 3: Expand via edges (required, not optional)

After finding matches, ALWAYS check the `edges` array from Step 1 for connections:
1. Look at edges involving your matched files
2. Check `top_connections` — if any `source_chunk`/`target_chunk` names are related to the query topic, the connected file likely has relevant content too
3. If the connected file wasn't already in your candidate set, read its `chunks.json` and search for related content
4. Use `source_id`/`target_id` to jump directly to specific related chunks

**Why this matters**: Documents often split related information across files. Edges reveal these connections.

## Response Guidelines

- **Multi-source**: Synthesize information from ALL matched files, not just one
- **Cite sources**: Include document name and chunk path for each piece of information
- **Show connections**: When edges link matched chunks across files, mention the relationship
- **Distinguish**: Be transparent about what comes from parsed documents vs general knowledge
- **Use summaries**: When available, `metadata.summary` gives a quick overview without reading full content
