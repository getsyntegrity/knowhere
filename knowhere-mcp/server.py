"""
Knowhere MCP Server — 4-Tier Document Retrieval + Cloud Parsing.

A single MCP server exposing both Cloud API tools (parse documents)
and Local tools (navigate and search knowledge bases).

4-Tier Retrieval Architecture:
  Tier 1: knowhere-kb semantic retrieval (when installed)
  Tier 2: LLM-as-Retriever — agent navigates knowledge graph + hierarchy
    - get_knowledge_map        → see all files, keywords, importance, edges
    - get_document_structure   → see document's chapter/section TOC
    - read_document_chunks     → read specific sections' content
    - discover_relevant_files  → bottom-up grep to find files by content
  Tier 3: search_knowledge     → code-level keyword search (fallback)
  Tier 4: (no tool needed)     → agent reads files directly

Cloud tools (require KNOWHERE_API_KEY):
  - parse_document       — submit a URL for parsing
  - get_job_status       — check job progress
  - get_parsed_chunks    — download structured results

Usage:
    export KNOWHERE_API_KEY="sk_live_..."   # optional, for cloud tools
    python server.py              # stdio mode (for Claude Desktop / Cursor)
    fastmcp dev server.py         # interactive dev UI
"""

import io
import json
import os
import time
import zipfile

import requests
from fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE = "https://api.knowhereto.ai"
POLL_INTERVAL = 5       # seconds between status checks
POLL_TIMEOUT  = 300     # max seconds to wait for a job (5 min)

mcp = FastMCP(
    "Knowhere",
    instructions=(
        "Knowhere: parse documents into structured RAG-ready chunks, and search "
        "your local knowledge base. Use the LLM-as-Retriever workflow for best results: "
        "1) get_knowledge_map → 2) get_document_structure → 3) read_document_chunks. "
        "Use search_knowledge as fallback when navigation is not needed. "
        "Cloud tools require KNOWHERE_API_KEY."
    ),
)


# ── Cloud API Helpers ─────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """Get API key from environment."""
    key = os.environ.get("KNOWHERE_API_KEY", "")
    if not key:
        raise ValueError(
            "KNOWHERE_API_KEY environment variable is not set. "
            "Get your key at https://knowhereto.ai/login"
        )
    return key


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _download_chunks(result_url: str, max_chunks: int = 20) -> dict:
    """Download result ZIP and extract chunks.json."""
    try:
        resp = requests.get(result_url, timeout=60)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            file_list = zf.namelist()

            chunks_data = {}
            for name in file_list:
                if name.endswith("chunks.json"):
                    chunks_data = json.loads(zf.read(name))
                    break

            all_chunks = chunks_data.get("chunks", [])
            total = len(all_chunks)

            preview_chunks = []
            for chunk in all_chunks[:max_chunks]:
                preview = {
                    "type": chunk.get("type", "unknown"),
                    "content": chunk.get("content", "")[:500],
                    "metadata": chunk.get("metadata", {}),
                }
                if len(chunk.get("content", "")) > 500:
                    preview["content_truncated"] = True
                preview_chunks.append(preview)

            return {
                "total_count": total,
                "showing": len(preview_chunks),
                "chunks": preview_chunks,
                "result_files": file_list,
                "result_url": result_url,
            }
    except zipfile.BadZipFile:
        return {"error": "Result is not a valid ZIP file.", "result_url": result_url}
    except Exception as e:
        return {"error": str(e), "result_url": result_url}


# ══════════════════════════════════════════════════════════════════════════════
#  CLOUD TOOLS (require KNOWHERE_API_KEY)
# ══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def parse_document(
    source_url: str,
    wait_for_completion: bool = True,
    max_chunks_preview: int = 5,
) -> dict:
    """Parse a document from a public URL into structured chunks.

    Submits the document to Knowhere API for parsing. By default waits for
    completion and returns the parsed chunks directly.

    Args:
        source_url: Public URL of the document (PDF, DOCX, XLSX, PPTX, etc.)
        wait_for_completion: If True, polls until done (up to 5 min). If False, returns immediately with job_id.
        max_chunks_preview: Number of chunks to include in the preview (default 5).

    Returns:
        dict with job_id, status, and optionally parsed chunks preview.
    """
    resp = requests.post(
        f"{API_BASE}/v1/jobs",
        headers=_headers(),
        json={"source_type": "url", "source_url": source_url},
    )
    resp.raise_for_status()
    job = resp.json()
    job_id = job.get("job_id")

    if not wait_for_completion:
        return {
            "job_id": job_id,
            "status": job.get("status", "pending"),
            "message": "Job submitted. Use get_job_status() to check progress.",
        }

    # Poll for completion
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        status_resp = requests.get(
            f"{API_BASE}/v1/jobs/{job_id}",
            headers=_headers(),
        )
        status_resp.raise_for_status()
        job = status_resp.json()
        status = job.get("status", "unknown")

        if status == "done":
            result_url = job.get("result_url")
            if result_url:
                chunks = _download_chunks(result_url, max_chunks_preview)
                return {
                    "job_id": job_id,
                    "status": "done",
                    "result_url": result_url,
                    "total_chunks": chunks.get("total_count", 0),
                    "chunks_preview": chunks.get("chunks", []),
                }
            return {"job_id": job_id, "status": "done", "result_url": result_url}

        elif status == "failed":
            return {
                "job_id": job_id,
                "status": "failed",
                "error": job.get("error", "Unknown error"),
            }

    return {
        "job_id": job_id,
        "status": "timeout",
        "message": f"Job did not complete within {POLL_TIMEOUT}s. "
                   f"Use get_job_status('{job_id}') to check later.",
    }


@mcp.tool()
def get_job_status(job_id: str) -> dict:
    """Check the status of a previously submitted parsing job.

    Args:
        job_id: The job ID returned by parse_document().

    Returns:
        dict with status, result_url (if done), or error (if failed).
    """
    resp = requests.get(
        f"{API_BASE}/v1/jobs/{job_id}",
        headers=_headers(),
    )
    resp.raise_for_status()
    job = resp.json()
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "result_url": job.get("result_url"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
    }


@mcp.tool()
def get_parsed_chunks(
    job_id: str,
    max_chunks: int = 20,
) -> dict:
    """Download and extract parsed chunks from a completed job.

    First checks job status. If done, downloads the result ZIP and extracts
    the structured chunks from chunks.json.

    Args:
        job_id: The job ID of a completed parsing job.
        max_chunks: Maximum number of chunks to return (default 20).

    Returns:
        dict with chunks array, total_count, and available files in the result package.
    """
    resp = requests.get(
        f"{API_BASE}/v1/jobs/{job_id}",
        headers=_headers(),
    )
    resp.raise_for_status()
    job = resp.json()

    if job.get("status") != "done":
        return {
            "job_id": job_id,
            "status": job.get("status"),
            "message": "Job is not yet complete. Try again later.",
        }

    result_url = job.get("result_url")
    if not result_url:
        return {"job_id": job_id, "error": "No result_url available."}

    return _download_chunks(result_url, max_chunks)


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 2: LLM-as-Retriever (Agent navigates knowledge base)
# ══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def get_knowledge_map(kb_id: str = "") -> dict:
    """Get a bird's-eye view of your knowledge base.

    Returns all documents with their keywords, importance scores, chunk counts,
    and cross-file connections. Use this FIRST to understand what's available
    and decide which documents to explore.

    Recommended workflow:
    1. get_knowledge_map() → see all files
    2. get_document_structure(kb_id, doc_name) → see chapter/section TOC
    3. read_document_chunks(kb_id, doc_name, section_path) → read content

    Args:
        kb_id: Optional. Specify a KB ID to see only that KB. Leave empty for all.

    Returns:
        dict with knowledge base overview including files, keywords, and edges.
    """
    from local_search import do_get_knowledge_map
    return do_get_knowledge_map(kb_id or None)


@mcp.tool()
def get_document_structure(kb_id: str, doc_name: str) -> dict:
    """Get the chapter/section structure (TOC) of a specific document.

    Returns the document's hierarchy tree so you can decide which sections
    are relevant to the user's question before reading the actual content.

    Args:
        kb_id: Knowledge base ID (from get_knowledge_map).
        doc_name: Document name (from get_knowledge_map's files list).

    Returns:
        dict with document hierarchy/TOC tree.
    """
    from local_search import do_get_document_structure
    return do_get_document_structure(kb_id, doc_name)


@mcp.tool()
def read_document_chunks(
    kb_id: str,
    doc_name: str,
    section_path: str = "",
    max_chunks: int = 50,
) -> dict:
    """Read the actual content chunks from a document.

    If section_path is specified, returns only chunks from that section
    (e.g. "一、工程概况/1.工程概况和特点"). This reduces token usage
    by focusing on relevant sections.

    Args:
        kb_id: Knowledge base ID.
        doc_name: Document name.
        section_path: Optional. Section path prefix to filter chunks.
        max_chunks: Maximum chunks to return (default 50).

    Returns:
        dict with chunks array containing type, path, content, summary.
    """
    from local_search import do_read_chunks
    return do_read_chunks(kb_id, doc_name, section_path or None, max_chunks)


@mcp.tool()
def discover_relevant_files(query: str, kb_id: str = "") -> dict:
    """Bottom-up file discovery: find which documents contain query terms.

    Searches ALL chunks across knowledge bases for the query terms and
    returns file names with hit counts. Use this to complement the top-down
    approach (get_knowledge_map) — union both results for best coverage.

    This is lightweight: returns only file names and hit counts, NOT content.

    Args:
        query: Search query (supports Chinese and English).
        kb_id: Optional. Limit search to specific KB.

    Returns:
        dict with discovered_files list sorted by hit_count.
    """
    from local_search import do_discover_files
    return do_discover_files(query, kb_id or None)


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 3: Code-Level Keyword Search (Fallback)
# ══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def search_knowledge(query: str, top_k: int = 5) -> dict:
    """Search your local knowledge base using keyword matching (Tier 3 fallback).

    Performs keyword search across all knowledge bases, scoring chunks by
    content hits, summary relevance, and keyword overlap. Use the Tier 2
    navigation tools (get_knowledge_map → get_document_structure →
    read_document_chunks) for better results.

    Args:
        query: Search query (supports Chinese and English).
        top_k: Number of results to return (default 5).

    Returns:
        dict with search results including content previews, scores, and related chunks.
    """
    from local_search import do_search
    return do_search(query, top_k)


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
