import sys
import types

from app.core.runtime_limits import (
    NATIVE_THREAD_CAPS,
    apply_native_thread_caps,
    read_pymupdf_max_concurrent,
)


def test_read_pymupdf_max_concurrent_uses_shared_settings(monkeypatch):
    fake_config = types.ModuleType("shared.core.config")
    fake_config.settings = types.SimpleNamespace(PYMUPDF_MAX_CONCURRENT=3)

    monkeypatch.setitem(sys.modules, "shared.core.config", fake_config)

    assert read_pymupdf_max_concurrent() == 3


def test_apply_native_thread_caps_sets_missing_values():
    env: dict[str, str] = {}

    applied_caps = apply_native_thread_caps(env)

    assert applied_caps == NATIVE_THREAD_CAPS
    assert env == NATIVE_THREAD_CAPS


def test_apply_native_thread_caps_overrides_existing_values():
    env = {
        "OMP_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "4",
    }

    applied_caps = apply_native_thread_caps(env)

    assert applied_caps["OMP_NUM_THREADS"] == "1"
    assert applied_caps["MKL_NUM_THREADS"] == "1"
    assert env["OMP_NUM_THREADS"] == "1"
    assert env["MKL_NUM_THREADS"] == "1"

    for env_var, default_value in NATIVE_THREAD_CAPS.items():
        assert applied_caps[env_var] == default_value
        assert env[env_var] == default_value
