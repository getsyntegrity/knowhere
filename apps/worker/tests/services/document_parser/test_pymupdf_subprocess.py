"""Tests for pymupdf_subprocess — spawn, timeout, error handling."""
import os
import sys
import time
import types

import pytest

# ─── Mock external dependencies not available in test env ─────────

# Fake gevent module
_fake_gevent = types.ModuleType("gevent")


class _FakeThreadpool:
    @staticmethod
    def apply(fn, args):
        fn(*args)


class _FakeHub:
    threadpool = _FakeThreadpool()


def _get_hub():
    return _FakeHub()


_fake_gevent.get_hub = _get_hub
sys.modules.setdefault("gevent", _fake_gevent)


# Fake shared.core.exceptions hierarchy for domain exception imports
class _FakePDFParsingException(Exception):
    def __init__(self, user_message="", reason="", internal_message="", **kwargs):
        super().__init__(internal_message or user_message)
        self.user_message = user_message
        self.reason = reason
        self.internal_message = internal_message


class _FakeTimeoutException(Exception):
    def __init__(self, internal_message="", retry_after=0, **kwargs):
        super().__init__(internal_message)
        self.internal_message = internal_message
        self.retry_after = retry_after


_fake_domain = types.ModuleType("shared.core.exceptions.domain_exceptions")
_fake_domain.PDFParsingException = _FakePDFParsingException
_fake_domain.TimeoutException = _FakeTimeoutException

# Register the full module path hierarchy
for mod_name in [
    "shared", "shared.core", "shared.core.exceptions",
    "shared.core.exceptions.domain_exceptions",
]:
    sys.modules.setdefault(mod_name, types.ModuleType(mod_name))
sys.modules["shared.core.exceptions.domain_exceptions"] = _fake_domain

from app.services.document_parser.pymupdf_subprocess import run_in_child_process, worker


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

    def test_happy_path(self):
        result = run_in_child_process(_ok_worker, 3, 4)
        assert result["ok"] is True
        assert result["result"] == 7

    def test_worker_failure_raises_pdf_parsing_exception(self):
        with pytest.raises(_FakePDFParsingException) as exc_info:
            run_in_child_process(_failing_worker)
        assert "something went wrong" in exc_info.value.internal_message
        assert exc_info.value.reason == "SUBPROCESS_FAILED"

    def test_worker_crash_raises_pdf_parsing_exception(self):
        with pytest.raises(_FakePDFParsingException) as exc_info:
            run_in_child_process(_crash_worker, timeout=5)
        assert exc_info.value.reason == "SUBPROCESS_CRASH"

    def test_worker_timeout_raises_timeout_exception(self):
        with pytest.raises(_FakeTimeoutException) as exc_info:
            run_in_child_process(_slow_worker, timeout=1)
        assert exc_info.value.retry_after == 30

    def test_file_io_from_child(self, tmp_path):
        output_path = str(tmp_path / "output.txt")
        result = run_in_child_process(_file_writing_worker, output_path)

        assert result["ok"] is True
        assert os.path.exists(output_path)
        with open(output_path) as f:
            assert f.read() == "hello from child"

    def test_worker_decorator_happy_path(self):
        result = run_in_child_process(_decorated_ok_worker, 3, 4)
        assert result["ok"] is True
        assert result["result"] == 12

    def test_worker_decorator_catches_exception(self):
        with pytest.raises(_FakePDFParsingException) as exc_info:
            run_in_child_process(_decorated_raising_worker)
        assert "decorated failure" in exc_info.value.internal_message
