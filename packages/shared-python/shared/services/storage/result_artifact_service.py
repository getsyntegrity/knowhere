from __future__ import annotations

MEDIA_ASSET_DIRS = {"images", "tables"}


def normalize_client_result_artifact_path(file_path: str | None) -> str | None:
    if not file_path:
        return None
    normalized = str(file_path).strip().replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
    if len(parts) < 2 or parts[0] not in MEDIA_ASSET_DIRS:
        return None
    return "/".join(parts)


def build_result_artifact_storage_key(*, job_id: str, artifact_ref: str) -> str:
    normalized_ref = normalize_client_result_artifact_path(artifact_ref)
    if not normalized_ref:
        raise ValueError(f"Invalid client result artifact ref: {artifact_ref}")
    return f"results/{job_id}/{normalized_ref}"
