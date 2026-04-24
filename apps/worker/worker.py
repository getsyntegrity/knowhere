#!/usr/bin/env python3
# ruff: noqa: E402
# CRITICAL: Monkey patch MUST be the very first thing before ANY other imports.
# This patches stdlib (socket, ssl, threading, etc.) for cooperative greenlet scheduling.
import gevent.monkey

gevent.monkey.patch_all()

# Patch psycopg2 for cooperative DB access under gevent.
from psycogreen.gevent import patch_psycopg

patch_psycopg()

from app.core.runtime_limits import apply_native_thread_caps

apply_native_thread_caps()


def main() -> None:
    """Start the full worker bootstrap only in the main worker process."""
    from app.core.worker_bootstrap import run_worker

    run_worker()


if __name__ == "__main__":
    main()
