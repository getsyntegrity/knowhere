---
name: knowhere_memory
description: Auto-discover and search knowledge from Knowhere parsed documents. Use when the user asks questions, needs information, or references their knowledge base. Also handles document ingestion when files are uploaded.
user-invocable: false
---

# Knowhere Knowledge Memory

This agent has access to a **personal knowledge base** managed by Knowhere. The knowledge base stores parsed documents as structured JSON files under `~/.knowhere/`.

## When to Use

Activate this skill when:

- The user asks a question that might be answered by their documents
- The user says "look it up", "help me find", "knowledge base", "my materials", etc.
- The user asks "what materials do I have" or wants an overview
- A file is uploaded or attached (trigger ingestion)

## Part 1: Ingesting New Documents

When a file is uploaded or attached (e.g. via Telegram), the agent should parse it into the knowledge base.

### Attachment markers

When a prompt contains a marker like:

```text
[media attached: /absolute/path/to/file.pdf (application/pdf) | handbook.pdf]
```

Use the exact absolute path as `filePath` and the visible filename as `fileName`.

### Ingestion workflow

1. Call `knowhere_ingest_document` with the file path
2. The plugin handles everything automatically:
   - Uploads the file to Knowhere API for parsing
   - Polls until parsing completes
   - Downloads and extracts the result package
   - **Automatically** copies parsed data to `~/.knowhere/{kbId}/`
   - **Automatically** builds/updates `knowledge_graph.json`
3. After ingest completes, the new document is immediately searchable via the retrieval workflow below

Supported formats: PDF, DOCX, XLSX, PPTX, TXT, MD, images (JPG, PNG)

## Part 2: Retrieving Knowledge

### Data Location

All knowledge data lives under `~/.knowhere/{kb_id}/`:

```text
~/.knowhere/
└── {kb_id}/                          # e.g. "telegram"
    ├── knowledge_graph.json          # File-level overview + cross-file edges
    ├── chunk_stats.json              # Usage stats per chunk
    └── {document_name}/              # One subdir per parsed document
        ├── chunks.json               # All chunks (the actual content)
        ├── hierarchy.json            # Document structure tree
        ├── images/                   # Extracted images
        └── tables/                   # Extracted tables (HTML)
```

### Strategy: Prefer tools, fall back to files

#### If `knowhere_kg_list` / `knowhere_kg_query` tools are available → use them

These tools provide efficient access to the knowledge graph:

1. `knowhere_kg_list` — list all available knowledge bases
2. `knowhere_kg_query(kbId)` — returns the full knowledge graph (files, keywords, edges)
3. Then read individual `chunks.json` files with your file reading tool for detailed content

#### If no KG tools are available → self-navigate using file tools

Follow this pattern — do NOT explore the filesystem blindly:

**Step 0: Resolve kb_id**

- List only the top level of `~/.knowhere/` to discover available KB IDs
- If exactly one KB → use it. If multiple → ask the user which one

**Step 1: Read knowledge_graph.json**

Read `~/.knowhere/{kb_id}/knowledge_graph.json`:

```json
{
  "version": "2.0",
  "stats": { "total_files": 5, "total_chunks": 327 },
  "files": {
    "report.docx": {
      "chunks_count": 198,
      "types": { "text": 135, "table": 21, "image": 42 },
      "top_keywords": ["excavation", "retaining", "construction"],
      "importance": 0.85
    }
  },
  "edges": [
    {
      "source": "file_A.docx",
      "target": "file_B.pdf",
      "connection_count": 20,
      "top_connections": [{ "source_chunk": "Chapter 3", "target_chunk": "Safety Policy", "score": 1.0 }]
    }
  ]
}
```

Match user query against ALL files' `top_keywords`. Prioritize by `importance`.

**Step 2: Read chunks.json for each candidate file**

Read `~/.knowhere/{kb_id}/{document_name}/chunks.json`:

```json
{
  "chunks": [{
    "chunk_id": "uuid",
    "type": "text | table | image",
    "path": "Default_Root/doc.pdf/Chapter 1/1.1",
    "content": "actual content...",
    "metadata": {
      "summary": "LLM-generated summary",
      "keywords": ["extracted", "keywords"],
      "length": 1234
    }
  }]
}
```

Search `content` and `metadata.keywords` against the user's query.

**Step 3: Expand via edges (do not skip)**

Check `edges` from Step 1 for cross-document connections. If related files weren't in your candidate set, read their `chunks.json` too.

## Response Guidelines

- **Cite sources**: include document name and section path
- **Multi-source**: synthesize from ALL matched files, not just the first hit
- **Show connections**: mention cross-file relationships from edges
- **No internal IDs**: never expose `chunk_id` or UUID paths to the user
- **User's language**: reply in the same language the user is using
