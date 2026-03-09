import time
from pathlib import Path

import pytest

import shared.services.worker_health as mod


def test_assert_worker_healthy_passes_for_fresh_heartbeat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    heartbeat_path = tmp_path / "worker-heartbeat.json"
    monkeypatch.setattr(mod, "HEARTBEAT_PATH", heartbeat_path)
    monkeypatch.setattr(mod, "HEARTBEAT_STALE_AFTER_SECONDS", 10.0)

    mod.write_worker_heartbeat()

    mod.assert_worker_healthy()


def test_assert_worker_healthy_raises_for_stale_heartbeat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    heartbeat_path = tmp_path / "worker-heartbeat.json"
    monkeypatch.setattr(mod, "HEARTBEAT_PATH", heartbeat_path)
    monkeypatch.setattr(mod, "HEARTBEAT_STALE_AFTER_SECONDS", 0.01)

    mod.write_worker_heartbeat()
    time.sleep(0.02)

    with pytest.raises(SystemExit, match="stale"):
        mod.assert_worker_healthy()
