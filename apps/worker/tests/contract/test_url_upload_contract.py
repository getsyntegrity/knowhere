from __future__ import annotations

import os
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.engine import Engine

from support.contract_database import insert_contract_job, insert_contract_user


def _load_upload_task_modules() -> tuple[Any, Engine, Any, Any]:
    import app.core.tasks.kb_tasks as kb_tasks
    from shared.core.database_sync import get_sync_engine
    from shared.services.redis.redis_sync_service import (
        SyncJobInfoRedisService,
        SyncRedisServiceFactory,
    )

    return kb_tasks, get_sync_engine(), SyncJobInfoRedisService, SyncRedisServiceFactory


def test_should_upload_a_url_job_to_the_expected_storage_key_and_publish_progress(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    kb_tasks, engine, sync_job_info_service_cls, sync_redis_service_factory = (
        _load_upload_task_modules()
    )

    user_id = f"worker-user-{uuid4().hex[:12]}"
    job_id = f"job_url_upload_{uuid4().hex[:12]}"
    source_url = "https://example.test/files/contract-source.pdf"
    s3_key = f"uploads/{job_id}.pdf"
    downloaded_path = tmp_path / "downloaded-contract-source.pdf"
    uploaded_calls: list[tuple[str, str, str]] = []

    def resolve_public_address(
        host: str,
        port: int | None,
    ) -> list[tuple[socket.AddressFamily, socket.SocketKind, int, str, tuple[str, int]]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(
        kb_tasks,
        "download_file_from_url",
        lambda _source_url: str(downloaded_path),
    )
    monkeypatch.setattr(
        kb_tasks,
        "upload_to_s3",
        lambda local_path, storage_key, bucket: uploaded_calls.append(
            (local_path, storage_key, bucket)
        ),
    )
    monkeypatch.setattr(
        kb_tasks,
        "verify_s3_file_exists",
        lambda storage_key: {"exists": storage_key == s3_key, "size": 3},
    )
    monkeypatch.setattr(socket, "getaddrinfo", resolve_public_address)

    downloaded_path.write_bytes(b"pdf")

    with engine.begin() as connection:
        insert_contract_user(connection, user_id=user_id)
        insert_contract_job(
            connection,
            job_id=job_id,
            user_id=user_id,
            status="waiting-file",
            source_type="url",
            s3_key=s3_key,
            job_metadata={
                "namespace": "worker-contract",
                "source_type": "url",
                "source_url": source_url,
                "source_file_name": "contract-source.pdf",
            },
        )

    redis_service = sync_redis_service_factory.get_service()
    sync_job_info_service = sync_job_info_service_cls(redis_service)
    sync_job_info_service.save_job_info(
        job_id,
        {
            "job_id": job_id,
            "s3_key": s3_key,
            "user_id": user_id,
            "webhook_enabled": False,
            "job_type": "kb_management",
            "source_type": "url",
        },
    )

    result = kb_tasks.upload_url_file_task.run(
        job_id,
        source_url,
        user_id,
        "kb_management",
    )

    assert result == {
        "status": "success",
        "job_id": job_id,
        "s3_key": s3_key,
        "file_size": 3,
    }
    assert uploaded_calls == [
        (str(downloaded_path), s3_key, kb_tasks.settings.S3_BUCKET_NAME),
    ]
    assert os.path.exists(downloaded_path) is False

    progress = redis_service.hgetall(f"task:{job_id}:progress")
    assert progress["progress"] == 100
    assert progress["message"] == "URL file upload complete, waiting for processing..."
    assert progress["timestamp"]

    with engine.begin() as connection:
        job_row = (
            connection.execute(
                text(
                    """
                    SELECT status, source_type, s3_key
                    FROM jobs
                    WHERE job_id = :job_id
                    """
                ),
                {"job_id": job_id},
            )
            .mappings()
            .one()
        )

    assert job_row["status"] == "waiting-file"
    assert job_row["source_type"] == "url"
    assert job_row["s3_key"] == s3_key


def test_should_download_a_url_file_through_a_pinned_public_ip(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    import app.services.storage.sync_storage_service as sync_storage_service

    source_url = "https://example.test/files/contract-source.pdf"
    pinned_ip = "93.184.216.34"
    validation_calls: list[tuple[str, str]] = []
    download_calls: list[dict[str, object]] = []

    def fake_validate_public_http_url_and_resolve_ip(
        url: str,
        field: str = "url",
    ) -> SimpleNamespace:
        validation_calls.append((url, field))
        return SimpleNamespace(url=url, validated_ip=pinned_ip)

    def fake_download_pinned_outbound_file(
        *,
        url: str,
        pinned_ip: str,
        timeout_seconds: float,
        user_agent: str,
        temp_dir: str | None = None,
        field: str = "source_url",
    ) -> SimpleNamespace:
        download_calls.append(
            {
                "url": url,
                "pinned_ip": pinned_ip,
                "timeout_seconds": timeout_seconds,
                "user_agent": user_agent,
                "temp_dir": temp_dir,
                "field": field,
            }
        )
        temp_file_path = Path(temp_dir or tmp_path) / "downloaded-contract-source.pdf"
        temp_file_path.write_bytes(b"pdf")
        return SimpleNamespace(status=200, temp_file_path=str(temp_file_path))

    monkeypatch.setattr(
        sync_storage_service,
        "validate_public_http_url_and_resolve_ip",
        fake_validate_public_http_url_and_resolve_ip,
    )
    monkeypatch.setattr(
        sync_storage_service,
        "download_pinned_outbound_file",
        fake_download_pinned_outbound_file,
    )
    monkeypatch.setattr(sync_storage_service.settings, "TMP_PATH", str(tmp_path))

    downloaded_path = sync_storage_service.download_file_from_url(source_url)

    assert validation_calls == [(source_url, "source_url")]
    assert download_calls == [
        {
            "url": source_url,
            "pinned_ip": pinned_ip,
            "timeout_seconds": 300,
            "user_agent": "Knowhere-FileDownloader/1.0",
            "temp_dir": str(tmp_path),
            "field": "source_url",
        }
    ]
    assert downloaded_path == str(tmp_path / "downloaded-contract-source.pdf")
    assert Path(downloaded_path).read_bytes() == b"pdf"
