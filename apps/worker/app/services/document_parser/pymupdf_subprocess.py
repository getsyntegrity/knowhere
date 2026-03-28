"""
Run PyMuPDF work in a spawned child process.

PyMuPDF's C extension is not safe under gevent's cooperative threading.
This module provides a single entry point that:
  1. Spawns a child via multiprocessing("spawn") — no fork hazards
  2. Waits via gevent threadpool — heartbeats stay alive
  3. Returns a plain dict result or raises RuntimeError/TimeoutError

Worker contract:
  - Must be a top-level function (picklable by spawn)
  - Decorated with @worker to handle error serialization automatically
  - Signature: (queue: Queue, *args) -> None
  - On success: queue.put({"ok": True, ...payload...})
  - On failure: handled by @worker decorator
"""

import functools
import multiprocessing
import time

from loguru import logger
from shared.core.exceptions.domain_exceptions import PDFParsingException, TimeoutException

# Default timeout for child processes (seconds)
DEFAULT_TIMEOUT = 300


def worker(fn):
    """Decorator that wraps a child-process worker with error handling.

    The decorated function still receives (queue, *args). On unhandled
    exception, the error is serialized to the queue as a plain dict
    so the parent can raise a clean RuntimeError.
    """
    @functools.wraps(fn)
    def wrapped(queue, *args):
        try:
            fn(queue, *args)
        except Exception as e:
            # Log in child before serializing — child stderr may be the only
            # trace if the parent loses the queue result.
            import traceback
            traceback.print_exc()
            queue.put({
                "ok": False,
                "error_type": type(e).__name__,
                "error_msg": str(e),
            })
    return wrapped


def run_in_child_process(
    worker_fn,
    *args,
    timeout: int = DEFAULT_TIMEOUT,
):
    """Spawn a child process for PyMuPDF work, wait in OS thread (gevent-safe).

    Args:
        worker_fn: Top-level function with signature (queue, *args) -> None.
        *args: Arguments forwarded to worker_fn after the queue.
        timeout: Max seconds to wait before killing the child.

    Returns:
        dict with at least {"ok": True, ...} from the worker.

    Raises:
        TimeoutError: Child did not finish within timeout.
        RuntimeError: Child exited abnormally or reported failure.
    """
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=worker_fn, args=(queue, *args))

    t0 = time.monotonic()
    proc.start()
    child_pid = proc.pid
    logger.info(
        f"[pymupdf-subprocess] started pid={child_pid} fn={worker_fn.__name__}"
    )

    # Block in OS thread so gevent loop stays responsive
    import gevent
    gevent.get_hub().threadpool.apply(proc.join, (timeout,))

    elapsed = time.monotonic() - t0

    if proc.is_alive():
        proc.kill()
        proc.join(timeout=5)
        logger.error(
            f"[pymupdf-subprocess] TIMEOUT pid={child_pid} fn={worker_fn.__name__} "
            f"after {timeout}s — child killed"
        )
        raise TimeoutException(
            internal_message=(
                f"pymupdf child timed out after {timeout}s: "
                f"fn={worker_fn.__name__}, pid={child_pid}"
            ),
            retry_after=30,
        )

    if queue.empty():
        logger.error(
            f"[pymupdf-subprocess] CRASH pid={child_pid} fn={worker_fn.__name__} "
            f"exitcode={proc.exitcode} elapsed={elapsed:.1f}s — no result on queue"
        )
        raise PDFParsingException(
            user_message="Failed to process your document. Please try again.",
            reason="SUBPROCESS_CRASH",
            internal_message=(
                f"pymupdf child exited with code={proc.exitcode} and no result: "
                f"fn={worker_fn.__name__}, pid={child_pid}"
            ),
        )

    result = queue.get_nowait()
    if not result.get("ok"):
        logger.error(
            f"[pymupdf-subprocess] FAILED pid={child_pid} fn={worker_fn.__name__} "
            f"elapsed={elapsed:.1f}s — {result.get('error_type')}: {result.get('error_msg')}"
        )
        raise PDFParsingException(
            user_message="Failed to process your document. Please try again.",
            reason="SUBPROCESS_FAILED",
            internal_message=(
                f"pymupdf child failed: {result.get('error_type')}: "
                f"{result.get('error_msg')}"
            ),
        )

    logger.info(
        f"[pymupdf-subprocess] done pid={child_pid} fn={worker_fn.__name__} "
        f"elapsed={elapsed:.1f}s"
    )
    return result
