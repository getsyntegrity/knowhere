from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from shared.core.config import settings
from shared.services.storage.result_artifact_service import (
    build_result_artifact_storage_key,
    normalize_client_result_artifact_path,
)

from app.services.storage.sync_storage_service import upload_to_s3

MEDIA_CHUNK_TYPES = {"image", "table"}


def publish_client_result_artifacts(*, job_id: str, chunks: list[dict[str, Any]], add_dir: str) -> list[dict[str, Any]]:
    """Publish client-facing result artifacts and attach canonical asset object keys.

    Current V1 scope publishes image/table assets only. The service boundary is
    broader than media so we can extend it later to other client-facing result
    artifacts without growing more worker-inline logic.
    """
    if not add_dir:
        return chunks

    results_bucket = getattr(settings, "S3_RESULTS_BUCKET", settings.S3_BUCKET_NAME)
    enriched_chunks: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_type = str(chunk.get("type") or chunk.get("chunk_type") or "").strip().split("\n", 1)[0].lower()
        metadata = dict(chunk.get("metadata") or {})
        enriched_chunk = {**chunk, "metadata": metadata}

        if chunk_type not in MEDIA_CHUNK_TYPES:
            enriched_chunks.append(enriched_chunk)
            continue

        artifact_path = normalize_client_result_artifact_path(
            metadata.get("file_path") or chunk.get("file_path")
        )
        if not artifact_path:
            enriched_chunks.append(enriched_chunk)
            continue

        local_artifact_path = Path(add_dir) / artifact_path
        if not local_artifact_path.is_file():
            logger.warning(
                f"Skipping result artifact publish; local artifact missing: "
                f"job_id={job_id}, artifact_path={artifact_path}, local_path={local_artifact_path}"
            )
            enriched_chunks.append(enriched_chunk)
            continue

        storage_key = build_result_artifact_storage_key(job_id=job_id, artifact_ref=artifact_path)
        upload_to_s3(str(local_artifact_path), storage_key, results_bucket)
        metadata["asset_ref"] = artifact_path
        enriched_chunks.append(enriched_chunk)

    return enriched_chunks
