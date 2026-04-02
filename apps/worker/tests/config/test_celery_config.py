import importlib.util
from pathlib import Path


def _load_celery_config_class() -> type[object]:
    module_path = (
        Path(__file__).resolve().parents[4]
        / "packages"
        / "shared-python"
        / "shared"
        / "core"
        / "config"
        / "celery.py"
    )
    spec = importlib.util.spec_from_file_location("test_celery_config_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.CeleryConfig


def test_prefers_explicit_celery_redis_url() -> None:
    CeleryConfig = _load_celery_config_class()
    config = CeleryConfig(
        CELERY_REDIS_URL="rediss://redis.example:6379/0?ssl_cert_reqs=CERT_NONE",
    )

    assert config.get_celery_redis_url() == (
        "rediss://redis.example:6379/0?ssl_cert_reqs=CERT_NONE"
    )
    assert config.get_celery_broker_url() == config.get_celery_redis_url()
    assert config.get_celery_result_backend() == config.get_celery_redis_url()


def test_uses_default_local_celery_redis_url() -> None:
    CeleryConfig = _load_celery_config_class()
    config = CeleryConfig()

    assert config.get_celery_redis_url() == "redis://localhost:6379/0"
