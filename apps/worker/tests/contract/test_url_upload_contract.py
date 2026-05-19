from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from pytest import MonkeyPatch

from support.worker_url_upload_contract import WorkerUrlUploadContract


class _SilentStaticFileHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _serve_directory(directory: Path) -> Iterator[str]:
    handler = partial(_SilentStaticFileHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_should_upload_a_url_job_to_the_expected_storage_key_and_publish_progress(
    worker_contract_environment: None,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "contract-source.pdf"
    source_file.write_bytes(b"pdf")

    contract = WorkerUrlUploadContract.create()
    contract.use_workspace_root(monkeypatch, tmp_path)
    contract.allow_private_url_sources(monkeypatch)

    with _serve_directory(source_dir) as server_url:
        source_url = f"{server_url}/{source_file.name}"
        job = contract.create_url_job(source_url=source_url)

        celery_result = contract.enqueue_upload_url_task(
            job_id=job["job_id"],
            source_url=source_url,
            user_id=job["user_id"],
        )

    assert celery_result.successful()
    assert celery_result.result == {
        "status": "success",
        "job_id": job["job_id"],
        "s3_key": job["s3_key"],
        "file_size": len(b"pdf"),
    }

    uploaded_source = contract.verify_uploaded_source_object(job["s3_key"])
    assert uploaded_source["exists"] is True
    assert uploaded_source["size"] == len(b"pdf")
    assert contract.read_uploaded_source_object(job["s3_key"]) == b"pdf"

    progress = contract.get_task_progress(job["job_id"])
    assert progress["progress"] == 100
    assert progress["message"] == "URL file upload complete, waiting for processing..."
    assert progress["timestamp"]

    job_row = contract.observe_job(job["job_id"])
    assert job_row["status"] == "waiting-file"
    assert job_row["source_type"] == "url"
    assert job_row["s3_key"] == job["s3_key"]
