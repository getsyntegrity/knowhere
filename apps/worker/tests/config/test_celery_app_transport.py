import importlib.util
import sys
import types
from pathlib import Path


class _FakeAppConfig:
    BROKER_POOL_LIMIT = 5

    def get_celery_broker_url(self) -> str:
        return "redis://localhost:6379/0"

    def get_celery_result_backend(self) -> str:
        return "redis://localhost:6379/0"

    def get_celery_redis_url(self) -> str:
        return "redis://localhost:6379/0"

    def get_task_priority(self, task_type: str) -> int:
        return 5

    def get_queue_name(self, task_type: str) -> str:
        return "default"


def _load_celery_app_module() -> types.ModuleType:
    shared_module = types.ModuleType("shared")
    core_module = types.ModuleType("shared.core")
    config_module = types.ModuleType("shared.core.config")
    config_module.app_config = _FakeAppConfig()

    sys.modules["shared"] = shared_module
    sys.modules["shared.core"] = core_module
    sys.modules["shared.core.config"] = config_module

    module_path = (
        Path(__file__).resolve().parents[4]
        / "packages"
        / "shared-python"
        / "shared"
        / "core"
        / "celery_app.py"
    )
    spec = importlib.util.spec_from_file_location("test_celery_app_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sets_cluster_safe_global_keyprefix() -> None:
    module = _load_celery_app_module()

    transport_options = module.celery_app.conf.broker_transport_options

    assert transport_options["visibility_timeout"] == 43200
    assert transport_options["retry_on_timeout"] is True
    assert transport_options["global_keyprefix"] == "{celery}"
