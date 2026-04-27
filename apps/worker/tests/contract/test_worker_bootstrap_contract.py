from __future__ import annotations

import sys


def test_should_register_worker_task_modules_for_celery_consumers(
    worker_contract_environment: None,
) -> None:
    from app.core import worker_bootstrap
    from shared.core.celery_app import celery_app

    expected_task_names: tuple[str, ...] = (
        "app.core.tasks.kb_tasks.upload_url_file_task",
        "app.core.tasks.kb_tasks.parse_task",
        "app.core.tasks.stale_job_sweeper.expire_stale_jobs",
        "app.core.tasks.webhook_tasks.recover_orphaned_webhooks",
    )
    task_module_names: tuple[str, ...] = (
        "app.core.tasks.kb_tasks",
        "app.core.tasks.stale_job_sweeper",
        "app.core.tasks.webhook_tasks",
    )

    for task_name in expected_task_names:
        celery_app.tasks.pop(task_name, None)

    for module_name in task_module_names:
        sys.modules.pop(module_name, None)

    worker_bootstrap._register_task_modules()

    for task_name in expected_task_names:
        assert task_name in celery_app.tasks
