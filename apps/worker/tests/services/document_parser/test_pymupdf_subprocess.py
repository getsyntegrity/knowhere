"""Tests for pymupdf_subprocess — spawn, timeout, error handling."""
import os
import time

import gevent
import pytest
from shared.core.exceptions.domain_exceptions import (
    PDFParsingException,
    TimeoutException,
)


import app.services.document_parser.pymupdf_subprocess as pymupdf_subprocess

run_in_child_process = pymupdf_subprocess.run_in_child_process
worker = pymupdf_subprocess.worker


@pytest.fixture(autouse=True)
def reset_process_pool():
    pymupdf_subprocess._shutdown_process_pool()
    yield
    pymupdf_subprocess._shutdown_process_pool()


# ─── Test workers (top-level for pickling) ────────────────────────

def _ok_worker(queue, x, y):
    """Simple worker that returns a sum."""
    queue.put({"ok": True, "result": x + y})


def _failing_worker(queue):
    """Worker that reports a failure."""
    queue.put({
        "ok": False,
        "error_type": "ValueError",
        "error_msg": "something went wrong",
    })


def _crash_worker(queue):
    """Worker that crashes without putting anything on the queue."""
    os._exit(1)


def _slow_worker(queue):
    """Worker that sleeps longer than any reasonable timeout."""
    time.sleep(60)
    queue.put({"ok": True})


def _file_writing_worker(queue, output_path):
    """Worker that writes a file, simulating real PyMuPDF work."""
    with open(output_path, "w") as f:
        f.write("hello from child")
    queue.put({"ok": True, "bytes_written": 16})


def _large_payload_worker(queue, payload_size):
    """Worker that returns enough data to overflow the Queue pipe buffer."""
    queue.put({"ok": True, "payload": "x" * payload_size})


def _sleep_result_worker(queue, sleep_seconds, value):
    """Worker that sleeps briefly, then returns a stable value."""
    time.sleep(sleep_seconds)
    queue.put({"ok": True, "result": value})


def _result_then_sleep_worker(queue, value, sleep_seconds):
    """Worker that publishes a result, then lingers before exiting."""
    queue.put({"ok": True, "result": value})
    time.sleep(sleep_seconds)


@worker
def _decorated_ok_worker(queue, x, y):
    """Worker using @worker decorator — no manual error handling."""
    queue.put({"ok": True, "result": x * y})


@worker
def _decorated_raising_worker(queue):
    """Worker using @worker decorator that raises."""
    raise ValueError("decorated failure")


# ─── Tests ────────────────────────────────────────────────────────

class TestRunInChildProcess:

    def test_process_pool_uses_gevent_threadpool(self):
        executor = pymupdf_subprocess._get_process_pool_executor()

        assert type(executor).__module__ == "gevent.threadpool"

    def test_happy_path(self):
        result = run_in_child_process(_ok_worker, 3, 4)
        assert result["ok"] is True
        assert result["result"] == 7

    def test_worker_failure_raises_pdf_parsing_exception(self):
        with pytest.raises(PDFParsingException) as exc_info:
            run_in_child_process(_failing_worker)
        assert "something went wrong" in exc_info.value.internal_message
        assert exc_info.value.details["reason"] == "SUBPROCESS_FAILED"

    def test_worker_crash_raises_pdf_parsing_exception(self):
        with pytest.raises(PDFParsingException) as exc_info:
            run_in_child_process(_crash_worker, timeout=5)
        assert exc_info.value.details["reason"] == "SUBPROCESS_CRASH"

    def test_worker_timeout_raises_timeout_exception(self):
        with pytest.raises(TimeoutException) as exc_info:
            run_in_child_process(_slow_worker, timeout=1)
        assert exc_info.value.retry_after == 30

    def test_file_io_from_child(self, tmp_path):
        output_path = str(tmp_path / "output.txt")
        result = run_in_child_process(_file_writing_worker, output_path)

        assert result["ok"] is True
        assert os.path.exists(output_path)
        with open(output_path) as f:
            assert f.read() == "hello from child"

    def test_large_payload_does_not_false_timeout(self):
        result = run_in_child_process(_large_payload_worker, 2_000_000, timeout=5)

        assert result["ok"] is True
        assert len(result["payload"]) == 2_000_000

    def test_slow_teardown_after_valid_result_does_not_fail(self):
        started_at = time.monotonic()
        result = run_in_child_process(_result_then_sleep_worker, "done", 10, timeout=5)
        elapsed = time.monotonic() - started_at

        assert result["ok"] is True
        assert result["result"] == "done"
        # The parent should return after the configured exit-grace/kill window,
        # not wait for the full lingering sleep in the child.
        max_expected_elapsed = (
            pymupdf_subprocess.POST_RESULT_EXIT_GRACE_SECONDS
            + pymupdf_subprocess.POST_KILL_JOIN_GRACE_SECONDS
            + 3
        )
        assert elapsed < max_expected_elapsed

    def test_queue_wait_does_not_consume_child_timeout(self, monkeypatch):
        monkeypatch.setattr(pymupdf_subprocess, "PROCESS_POOL_SIZE", 1)
        pymupdf_subprocess._shutdown_process_pool()

        first_greenlet = gevent.spawn(
            run_in_child_process,
            _sleep_result_worker,
            2,
            "first",
            timeout=5,
        )
        gevent.sleep(0.2)

        started_at = time.monotonic()
        second_greenlet = gevent.spawn(
            run_in_child_process,
            _sleep_result_worker,
            0.2,
            "second",
            timeout=5,
        )
        second = second_greenlet.get(timeout=10)
        elapsed = time.monotonic() - started_at

        first = first_greenlet.get(timeout=10)
        assert first["result"] == "first"
        assert second["result"] == "second"
        assert elapsed >= 2.0

    def test_timeout_does_not_abort_other_inflight_job(self, monkeypatch):
        monkeypatch.setattr(pymupdf_subprocess, "PROCESS_POOL_SIZE", 2)
        pymupdf_subprocess._shutdown_process_pool()

        healthy_greenlet = gevent.spawn(
            run_in_child_process,
            _sleep_result_worker,
            2,
            "healthy",
            timeout=10,
        )
        gevent.sleep(0.2)

        with pytest.raises(TimeoutException):
            run_in_child_process(_slow_worker, timeout=1)

        payload = healthy_greenlet.get(timeout=10)
        assert payload["result"] == "healthy"

    def test_worker_decorator_happy_path(self):
        result = run_in_child_process(_decorated_ok_worker, 3, 4)
        assert result["ok"] is True
        assert result["result"] == 12

    def test_worker_decorator_catches_exception(self):
        with pytest.raises(PDFParsingException) as exc_info:
            run_in_child_process(_decorated_raising_worker)
        assert "decorated failure" in exc_info.value.internal_message
