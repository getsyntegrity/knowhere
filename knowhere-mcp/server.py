"""
Knowhere MCP Server — Parse documents into structured data via MCP protocol.

Wraps the Knowhere REST API (https://api.knowhereto.ai) so any MCP-compatible
AI agent (Claude, Cursor, OpenAI Agents, etc.) can parse documents in one call.

Usage:
    export KNOWHERE_API_KEY="sk_live_..."
    python server.py              # stdio mode (for Claude Desktop / Cursor)
    fastmcp dev server.py         # interactive dev UI
"""

import os
import io
import json
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
        "Parse documents (PDF, DOCX, XLSX, PPTX) into structured, "
        "RAG-ready chunks with tables, images, and hierarchical metadata. "
        "Powered by Knowhere API (https://knowhereto.ai)."
    ),
)


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


# ── Tool 1: Parse a document from URL ────────────────────────────────────────
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
    # Create job
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
            # Fetch and extract chunks
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
        "message": f"Job did not complete within {POLL_TIMEOUT}s. Use get_job_status('{job_id}') to check later.",
    }


# ── Tool 2: Check job status ─────────────────────────────────────────────────
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


# ── Tool 3: Download and extract parsed chunks ───────────────────────────────
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
        max_chunks: Maximum number of chunks to return (default 20, to avoid context overflow).

    Returns:
        dict with chunks array, total_count, and available files in the result package.
    """
    # Check status first
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


# ── Helpers ───────────────────────────────────────────────────────────────────
def _download_chunks(result_url: str, max_chunks: int = 20) -> dict:
    """Download result ZIP and extract chunks.json."""
    try:
        resp = requests.get(result_url, timeout=60)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            file_list = zf.namelist()

            # Extract chunks.json
            chunks_data = {}
            for name in file_list:
                if name.endswith("chunks.json"):
                    chunks_data = json.loads(zf.read(name))
                    break

            all_chunks = chunks_data.get("chunks", [])
            total = len(all_chunks)

            # Truncate chunk content to avoid overwhelming agent context
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


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
