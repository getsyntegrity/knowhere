from __future__ import annotations

import ast
import json
import re
import tokenize
import tomllib
from io import StringIO
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[4]
CHINESE_TEXT_PATTERN: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff]")
PUBLICATION_HELPER_SCRIPT_PATHS: tuple[str, ...] = (
    "scripts/check-public.sh",
    "scripts/lint-public.sh",
    "scripts/scan-public-safety.sh",
    "scripts/test-public.sh",
    "scripts/test-public-shared.sh",
    "scripts/test-public-api.sh",
    "scripts/test-public-worker.sh",
    "scripts/typecheck-public.sh",
)
PUBLICATION_SCAN_ROOTS: tuple[str, ...] = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "docs",
    ".github",
    "apps",
    "packages/shared-python",
    "deploy",
)
PUBLICATION_SCAN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "patch markers leaked into tracked files",
        re.compile(
            r"\*\*\* Add File:|\*\*\* Update File:|\*\*\* Delete File:|\*\*\* Begin Patch|\*\*\* End Patch"
        ),
    ),
    (
        "credential-like material",
        re.compile(
            r"github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}"
        ),
    ),
    (
        "hardcoded private cloud identifiers",
        re.compile(
            r"arn:aws:[a-z0-9-]+:|[0-9]{12}\.dkr\.ecr\.[A-Za-z0-9-]+\.amazonaws\.com"
        ),
    ),
    (
        "private placeholder domains, staging hosts, or callback-provider hosts",
        re.compile(
            r"dev-placeholder@knowhere\.internal|knowhere\.internal|api-staging\.knowhereto\.ai|api\.internal|workers\.dev"
        ),
    ),
)


def read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def collect_docstrings(tree: ast.AST) -> list[str]:
    docstrings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Module,
                ast.ClassDef,
                ast.AsyncFunctionDef,
                ast.FunctionDef,
            ),
        ):
            docstring: str | None = ast.get_docstring(node, clean=False)
            if docstring:
                docstrings.append(docstring)
    return docstrings


def find_chinese_comments_and_docstrings(relative_path: str) -> list[str]:
    source_text: str = read_text(relative_path)
    snippets: list[str] = []

    tree = ast.parse(source_text, filename=relative_path)
    for docstring in collect_docstrings(tree):
        if CHINESE_TEXT_PATTERN.search(docstring):
            snippets.append(docstring.strip())

    for token in tokenize.generate_tokens(StringIO(source_text).readline):
        if token.type != tokenize.COMMENT:
            continue
        comment_text: str = token.string.lstrip("#").strip()
        if CHINESE_TEXT_PATTERN.search(comment_text):
            snippets.append(comment_text)

    return snippets


def iter_publication_scan_files() -> list[Path]:
    files_to_scan: list[Path] = []

    for relative_path in PUBLICATION_SCAN_ROOTS:
        root_path: Path = REPO_ROOT / relative_path
        candidate_paths: list[Path]

        if root_path.is_file():
            candidate_paths = [root_path]
        else:
            candidate_paths = sorted(
                path for path in root_path.rglob("*") if path.is_file()
            )

        for candidate_path in candidate_paths:
            relative_candidate_path: Path = candidate_path.relative_to(REPO_ROOT)
            relative_parts: tuple[str, ...] = relative_candidate_path.parts

            if candidate_path.name in {"uv.lock", "requirements.txt"}:
                continue

            if "__pycache__" in relative_parts:
                continue

            if "tests" in relative_parts or "__tests__" in relative_parts:
                continue

            files_to_scan.append(candidate_path)

    return files_to_scan


def find_publication_pattern_matches(pattern: re.Pattern[str]) -> list[str]:
    matched_paths: list[str] = []

    for file_path in iter_publication_scan_files():
        try:
            file_text: str = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if pattern.search(file_text):
            matched_paths.append(file_path.relative_to(REPO_ROOT).as_posix())

    return matched_paths


def test_publication_foundation_files_exist() -> None:
    for relative_path in (
        "LICENSE",
        "NOTICE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "pyproject.toml",
    ):
        assert (REPO_ROOT / relative_path).exists(), relative_path


def test_license_and_notice_match_apache_2_baseline() -> None:
    license_text: str = read_text("LICENSE")
    notice_text: str = read_text("NOTICE")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Knowhere API" in notice_text
    assert "Apache License, Version 2.0" in notice_text


def test_root_pyproject_exposes_python_workspace_members() -> None:
    pyproject_text: str = read_text("pyproject.toml")
    pyproject_data: dict[str, object] = tomllib.loads(pyproject_text)

    project_data: dict[str, object] = pyproject_data["project"]  # type: ignore[index]
    uv_workspace: dict[str, object] = pyproject_data["tool"]["uv"]["workspace"]  # type: ignore[index]

    assert project_data["name"] == "knowhere-api"
    assert project_data["requires-python"] == ">=3.11"
    assert uv_workspace["members"] == [
        "apps/api",
        "apps/worker",
        "packages/shared-python",
    ]


def test_gitignore_blocks_agent_artifacts_from_reappearing() -> None:
    gitignore_text: str = read_text(".gitignore")

    for ignored_path in (".cursor/", ".agent/", ".agent-hooks/", ".codex/"):
        assert ignored_path in gitignore_text


def test_private_root_only_files_are_removed_from_publication_branch() -> None:
    for relative_path in (
        "TASKS.md",
        "DOC_PROFILER_LOGIC.md",
        "AGENTS.md",
        "push_to_staging.sh",
        "sync_staging.sh",
        "line_clean",
    ):
        assert not (REPO_ROOT / relative_path).exists(), relative_path

    for relative_path in (".cursor", ".agent", ".agent-hooks"):
        assert not (REPO_ROOT / relative_path).exists(), relative_path


def test_private_debug_billing_scripts_are_removed_from_publication_branch() -> None:
    for relative_path in (
        "apps/api/test_methods.py",
        "apps/api/test_stripe.py",
    ):
        assert not (REPO_ROOT / relative_path).exists(), relative_path


def test_readme_links_public_foundation_documents() -> None:
    readme_text: str = read_text("README.md")

    assert "Apache 2.0" in readme_text
    assert "CONTRIBUTING.md" in readme_text
    assert "SECURITY.md" in readme_text
    assert "CODE_OF_CONDUCT.md" in readme_text


def test_build_images_workflow_only_targets_ghcr() -> None:
    workflow_text: str = read_text(".github/workflows/build-images.yml")

    assert "ghcr.io" in workflow_text
    assert "ALIYUN_ACR_" not in workflow_text
    assert "ECR_REGISTRY" not in workflow_text
    assert "AWS_EKS_" not in workflow_text
    assert "aws-actions/configure-aws-credentials" not in workflow_text
    assert "Login to ACR" not in workflow_text
    assert "Login to ECR" not in workflow_text
    assert "aws ecr get-login-password" not in workflow_text


def test_build_images_workflow_keeps_pr_permissions_read_only() -> None:
    workflow_text: str = read_text(".github/workflows/build-images.yml")

    assert "github.event_name == 'pull_request'" in workflow_text
    assert "github.event_name != 'pull_request'" in workflow_text
    assert "packages: read" in workflow_text
    assert "packages: write" in workflow_text


def test_repo_surface_is_python_first() -> None:
    readme_text: str = read_text("README.md")

    for removed_path in (
        "package.json",
        "pnpm-workspace.yaml",
        "pnpm-lock.yaml",
        "turbo.json",
        "packages/openapi-specs",
        "packages/shared-types",
        "apps/worker/app/sample_pdfs",
    ):
        assert not (REPO_ROOT / removed_path).exists(), removed_path

    for required_path in (".github/workflows/ci.yml",):
        assert (REPO_ROOT / required_path).exists(), required_path

    for removed_path in PUBLICATION_HELPER_SCRIPT_PATHS:
        assert not (REPO_ROOT / removed_path).exists(), removed_path

    assert "pnpm" not in readme_text
    assert "apps/web" not in readme_text
    assert "apps/docs" not in readme_text
    assert "sdk-typescript" not in readme_text
    assert "sdk-python" not in readme_text
    assert "shared-types" not in readme_text
    assert "openapi-specs" not in readme_text


def test_public_docs_cover_services_release_and_local_verification() -> None:
    readme_text: str = read_text("README.md")
    local_dev_readme_text: str = read_text("deploy/local-dev/README.md")
    external_services_text: str = read_text("docs/external-services.md")
    release_distribution_text: str = read_text("docs/release-distribution.md")
    self_hosting_text: str = read_text("docs/self-hosting.md")

    for relative_path in (
        "docs/external-services.md",
        "docs/release-distribution.md",
        "docs/self-hosting.md",
    ):
        assert (REPO_ROOT / relative_path).exists(), relative_path

    assert "docs/external-services.md" in readme_text
    assert "docs/release-distribution.md" in readme_text
    assert "docs/self-hosting.md" in readme_text

    assert "https://knowhereto.ai/" in external_services_text
    assert "PostgreSQL" in external_services_text
    assert "Redis" in external_services_text
    assert "S3-compatible storage" in external_services_text
    assert "MinerU" in external_services_text
    assert "QStash" in external_services_text
    assert "Stripe" in external_services_text
    assert "Resend" in external_services_text

    assert "source-code-only" in release_distribution_text
    assert "GHCR" in release_distribution_text
    assert "GitHub Release" in release_distribution_text

    assert "./start-dev.sh" in self_hosting_text
    assert "./stop-dev.sh" in self_hosting_text
    assert "curl http://localhost:5005/health" in self_hosting_text
    assert "curl http://localhost:5005/health" in local_dev_readme_text


def test_local_dev_bootstrap_docs_and_scripts_use_non_secret_demo_api_key() -> None:
    for relative_path in (
        "README.md",
        "deploy/local-dev/README.md",
        "deploy/local-dev/start-dev.sh",
        "apps/api/scripts/local_dev_bootstrap_service.py",
    ):
        file_text: str = read_text(relative_path)
        assert "sk_local_dev_tier5_full_access" not in file_text, relative_path


def test_public_env_examples_and_selected_dev_assets_are_english_first() -> None:
    api_env_text: str = read_text("apps/api/env.example")
    worker_env_text: str = read_text("apps/worker/env.example")

    for relative_path in (
        "apps/api/env.example",
        "apps/worker/env.example",
        "deploy/docker/Dockerfile.api",
        "deploy/docker/Dockerfile.worker",
        "deploy/local-dev/docker-compose.dev.yml",
        "deploy/local-dev/localstack/init/setup-aws-resources.sh",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path

    for env_text in (api_env_text, worker_env_text):
        assert "Copy this file to .env" in env_text
        assert "Required for local startup" in env_text
        assert "Required for specific features" in env_text
        assert "Optional or development-only" in env_text
        assert (
            "DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere"
            in env_text
        )
        assert "S3_ENDPOINT_URL=http://localhost:4566" in env_text
        assert "S3_ACCESS_KEY_ID=test" in env_text
        assert "S3_SECRET_ACCESS_KEY=test" in env_text
        assert "QSTASH_CALLBACK_BASE_URL=https://api.example.com/api/v1" in env_text
        assert (
            "DEFAULT_FOLDERS=Supplementary_Files,Temporary_Files,templates,images,fragments"
            in env_text
        )

    assert "知识库" not in api_env_text
    assert "复制此文件" not in api_env_text
    assert "知识库" not in worker_env_text
    assert "复制此文件" not in worker_env_text


def test_selected_shared_redis_and_storage_services_are_english_first() -> None:
    for relative_path in (
        "packages/shared-python/shared/services/redis/chunks_redis_service.py",
        "packages/shared-python/shared/services/redis/job_info_redis_service.py",
        "packages/shared-python/shared/services/redis/job_metadata_service.py",
        "packages/shared-python/shared/services/redis/rate_limit_service.py",
        "packages/shared-python/shared/services/redis/redis_alerts.py",
        "packages/shared-python/shared/services/redis/redis_monitor.py",
        "packages/shared-python/shared/services/redis/redis_service.py",
        "packages/shared-python/shared/services/redis/redis_sync_service.py",
        "packages/shared-python/shared/services/redis/task_redis_service.py",
        "packages/shared-python/shared/services/redis/user_redis_service.py",
        "packages/shared-python/shared/services/storage/adapters/oss_adapter.py",
        "packages/shared-python/shared/services/storage/adapters/s3_adapter.py",
        "packages/shared-python/shared/services/storage/file_encryptor_service.py",
        "packages/shared-python/shared/services/storage/file_upload_service.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_selected_api_and_shared_runtime_modules_are_english_first() -> None:
    for relative_path in (
        "apps/api/app/repositories/job_repository.py",
        "apps/api/app/repositories/job_result_repository.py",
        "apps/api/app/repositories/knowledge_base_repository.py",
        "apps/api/app/services/auth/api_key_service.py",
        "apps/api/app/services/billing/stripe_service.py",
        "packages/shared-python/shared/core/celery_router.py",
        "packages/shared-python/shared/core/database.py",
        "packages/shared-python/shared/models/database/knowledge_base.py",
        "packages/shared-python/shared/services/ai/response_process_service.py",
        "packages/shared-python/shared/utils/FileDownUpUtils.py",
        "packages/shared-python/shared/utils/device_utils.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_active_alembic_assets_and_local_init_files_are_public_safe() -> None:
    for relative_path in (
        "packages/shared-python/pyproject.toml",
        "apps/api/alembic/env.py",
        "apps/api/alembic.ini",
        "apps/api/alembic/versions/33eff537939b_baseline_20260305.py",
        "apps/api/scripts/reset_alembic.py",
        "deploy/local-dev/minio/init/setup-webhook.sh",
        "deploy/local-dev/mysql/init/01-init.sql",
        "deploy/local-dev/postgres/init/01-init.sql",
        "deploy/local-dev/localstack/init/setup-aws-resources.sh",
    ):
        file_text: str = read_text(relative_path)
        assert not CHINESE_TEXT_PATTERN.search(file_text), relative_path
        assert "*** Add File:" not in file_text, relative_path
        assert "*** Update File:" not in file_text, relative_path
        assert "*** Begin Patch" not in file_text, relative_path
        assert "*** End Patch" not in file_text, relative_path

    assert not (REPO_ROOT / "apps/api/alembic/versions_archive_20260305").exists()
    assert "knowhere.internal" not in read_text("README.md")


def test_selected_active_api_text_surfaces_are_english_first() -> None:
    for relative_path in (
        "apps/api/app/api/api_router.py",
        "apps/api/app/api/v1/api_v1.py",
        "apps/api/app/api/v1/health.py",
        "apps/api/app/api/v1/routes/api_key.py",
        "apps/api/app/api/v1/routes/jobs.py",
        "apps/api/app/api/v1/routes/knowledge_base.py",
        "apps/api/app/api/v1/routes/s3_events.py",
        "apps/api/app/api/v1/routes/version.py",
        "apps/api/app/middleware/moesif_middleware.py",
        "apps/api/app/services/knowledge/kb_orchestrator.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_selected_shared_python_public_surfaces_are_english_first() -> None:
    for relative_path in (
        "packages/shared-python/shared/core/config/ai.py",
        "packages/shared-python/shared/core/config/base.py",
        "packages/shared-python/shared/core/config/billing.py",
        "packages/shared-python/shared/core/config/database.py",
        "packages/shared-python/shared/core/config/redis.py",
        "packages/shared-python/shared/core/config/storage.py",
        "packages/shared-python/shared/models/schemas/api_key.py",
        "packages/shared-python/shared/models/schemas/billing.py",
        "packages/shared-python/shared/models/schemas/files.py",
        "packages/shared-python/shared/models/schemas/job.py",
        "packages/shared-python/shared/models/schemas/job_metadata.py",
        "packages/shared-python/shared/models/schemas/kb_user.py",
        "packages/shared-python/shared/models/schemas/knowledge_base.py",
        "packages/shared-python/shared/models/schemas/oss_event.py",
        "packages/shared-python/shared/models/schemas/s3_event.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_selected_api_support_surfaces_are_english_first() -> None:
    for relative_path in (
        "packages/shared-python/shared/core/config/app.py",
        "packages/shared-python/shared/models/schemas/dashboard.py",
        "packages/shared-python/shared/models/schemas/word.py",
        "apps/api/app/core/__init__.py",
        "apps/api/app/core/middleware/cors.py",
        "apps/api/app/core/response/ResponseCode.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_selected_module_support_surfaces_are_english_first() -> None:
    for relative_path in (
        "packages/shared-python/shared/core/state_machine/config.py",
        "packages/shared-python/shared/models/__init__.py",
        "packages/shared-python/shared/core/tasks/__init__.py",
        "packages/shared-python/shared/services/ai/__init__.py",
        "packages/shared-python/shared/services/storage/adapters/__init__.py",
        "apps/api/app/services/redis/__init__.py",
        "apps/api/app/core/image_cli.py",
        "apps/api/app/core/middleware/__init__.py",
        "packages/shared-python/shared/core/constants/api.py",
        "packages/shared-python/shared/core/constants/business.py",
        "packages/shared-python/shared/core/constants/system.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_selected_state_and_model_support_surfaces_are_english_first() -> None:
    for relative_path in (
        "packages/shared-python/shared/core/constants/__init__.py",
        "packages/shared-python/shared/core/state_machine/states.py",
        "packages/shared-python/shared/core/config/config.txt",
        "packages/shared-python/shared/models/database/job_result.py",
        "packages/shared-python/shared/models/database/payment_record.py",
        "packages/shared-python/shared/models/database/api_key.py",
        "packages/shared-python/shared/models/database/job.py",
        "packages/shared-python/shared/models/database/credits_transaction.py",
    ):
        assert not CHINESE_TEXT_PATTERN.search(read_text(relative_path)), relative_path


def test_selected_files_only_keep_english_comments_and_docstrings() -> None:
    for relative_path in (
        "packages/shared-python/shared/core/celery_router.py",
        "packages/shared-python/shared/core/database.py",
        "packages/shared-python/shared/core/security.py",
        "packages/shared-python/shared/utils/json_utils.py",
        "packages/shared-python/shared/utils/device_utils.py",
        "packages/shared-python/shared/models/database/job_state_audit_log.py",
        "packages/shared-python/shared/models/database/job_state_history.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_repository_files_only_keep_english_comments_and_docstrings() -> None:
    for relative_path in (
        "apps/api/app/repositories/base_repository.py",
        "apps/api/app/repositories/api_key_repository.py",
        "apps/api/app/repositories/payment_record_repository.py",
        "apps/api/app/repositories/stripe_price_config_repository.py",
        "apps/api/app/repositories/job_result_repository.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_large_repository_and_service_files_only_keep_english_comments_and_docstrings() -> (
    None
):
    for relative_path in (
        "apps/api/app/repositories/job_repository.py",
        "apps/api/app/repositories/knowledge_base_repository.py",
        "apps/api/app/services/auth/api_key_service.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_small_modules_only_keep_english_comments_and_docstrings() -> None:
    for relative_path in (
        "apps/api/app/repositories/__init__.py",
        "apps/worker/app/core/tasks/__init__.py",
        "apps/worker/app/services/__init__.py",
        "apps/worker/app/services/common/__init__.py",
        "packages/shared-python/shared/__init__.py",
        "packages/shared-python/shared/models/database/knowledge_base.py",
        "packages/shared-python/shared/models/database/stripe_price_config.py",
        "packages/shared-python/shared/services/ai/response_process_service.py",
        "packages/shared-python/shared/services/redis/__init__.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_utility_files_only_keep_english_comments_and_docstrings() -> None:
    assert not (REPO_ROOT / "apps/worker/tests/services/workload copy").exists()

    for relative_path in (
        "apps/worker/app/services/document_parser/atlas_parser.py",
        "apps/worker/tests/services/workload/test_page_estimator.py",
        "packages/shared-python/shared/core/constants/stopwords.py",
        "packages/shared-python/shared/services/ai/prompt_service.py",
        "packages/shared-python/shared/utils/file_utils.py",
        "packages/shared-python/shared/utils/gc_utils.py",
        "packages/shared-python/shared/utils/math_utils.py",
        "packages/shared-python/shared/utils/text_utils.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_redis_support_files_only_keep_english_comments_and_docstrings() -> (
    None
):
    for relative_path in (
        "packages/shared-python/shared/services/redis/chunks_redis_service.py",
        "packages/shared-python/shared/services/redis/job_info_redis_service.py",
        "packages/shared-python/shared/services/redis/job_metadata_service.py",
        "packages/shared-python/shared/services/redis/rate_limit_service.py",
        "packages/shared-python/shared/services/redis/redis_service_factory.py",
        "packages/shared-python/shared/services/redis/task_redis_service.py",
        "packages/shared-python/shared/services/redis/user_redis_service.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_redis_core_files_only_keep_english_comments_and_docstrings() -> None:
    for relative_path in (
        "packages/shared-python/shared/services/redis/redis_alerts.py",
        "packages/shared-python/shared/services/redis/redis_monitor.py",
        "packages/shared-python/shared/services/redis/redis_service.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_selected_storage_support_files_only_keep_english_comments_and_docstrings() -> (
    None
):
    for relative_path in (
        "packages/shared-python/shared/services/storage/adapters/oss_adapter.py",
        "packages/shared-python/shared/services/storage/adapters/s3_adapter.py",
        "packages/shared-python/shared/services/storage/file_encryptor_service.py",
        "packages/shared-python/shared/services/storage/storage_adapter.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_storage_upload_service_only_keeps_english_comments_and_docstrings() -> None:
    assert not find_chinese_comments_and_docstrings(
        "packages/shared-python/shared/services/storage/file_upload_service.py"
    )


def test_selected_worker_parser_files_only_keep_english_comments_and_docstrings() -> (
    None
):
    for relative_path in (
        "apps/worker/app/services/common/kb_utils.py",
        "apps/worker/app/services/document_parser/html_parser.py",
        "apps/worker/app/services/document_parser/image_parser.py",
        "apps/worker/app/services/document_parser/layout_parser.py",
        "apps/worker/app/services/document_parser/table_parser.py",
        "apps/worker/app/services/document_parser/toc_parser.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_remaining_support_files_only_keep_english_comments_and_docstrings() -> None:
    for relative_path in (
        "apps/worker/app/services/connect_builder/builder.py",
        "apps/worker/app/services/connect_builder/graph_builder.py",
        "apps/worker/app/services/connect_builder/summary_builder.py",
        "packages/shared-python/shared/core/constants/processing.py",
        "packages/shared-python/shared/utils/CommonHelper.py",
        "packages/shared-python/shared/utils/FileDownUpUtils.py",
        "packages/shared-python/shared/utils/redis_key_builder.py",
        "packages/shared-python/shared/utils/redis_retry.py",
    ):
        assert not find_chinese_comments_and_docstrings(relative_path), relative_path


def test_stripe_service_only_keeps_english_comments_and_docstrings() -> None:
    assert not find_chinese_comments_and_docstrings(
        "apps/api/app/services/billing/stripe_service.py"
    )


def test_workspace_pyprojects_use_uv_workspace_sources() -> None:
    api_pyproject_text: str = read_text("apps/api/pyproject.toml")
    worker_pyproject_text: str = read_text("apps/worker/pyproject.toml")

    assert "knowhere-shared = { workspace = true }" in api_pyproject_text
    assert "knowhere-shared = { workspace = true }" in worker_pyproject_text
    assert 'path = "../../packages/shared-python"' not in api_pyproject_text
    assert 'path = "../../packages/shared-python"' not in worker_pyproject_text


def test_readme_documents_inline_quality_commands() -> None:
    readme_text: str = read_text("README.md")

    for relative_path in PUBLICATION_HELPER_SCRIPT_PATHS:
        assert relative_path not in readme_text, relative_path

    assert "uv tool run --python 3.11 isort" in readme_text
    assert "uv tool run --python 3.11 black" in readme_text
    assert "uv run --python 3.11 pyright" in readme_text
    assert "uv run --python 3.11 pytest" in readme_text


def test_public_ci_workflow_uses_inline_quality_commands() -> None:
    ci_workflow_text: str = read_text(".github/workflows/ci.yml")

    for relative_path in PUBLICATION_HELPER_SCRIPT_PATHS:
        assert relative_path not in ci_workflow_text, relative_path

    assert (
        "python3.11 packages/shared-python/shared/tests/test_publication_foundation.py"
        in ci_workflow_text
    )
    assert "uv tool run --python 3.11 isort" in ci_workflow_text
    assert "uv tool run --python 3.11 black" in ci_workflow_text
    assert "uv run --python 3.11 pyright" in ci_workflow_text
    assert "uv run --python 3.11 pytest" in ci_workflow_text


def test_public_api_typecheck_baseline_targets_runtime_surface_only() -> None:
    pyright_config_text: str = read_text("apps/api/pyrightconfig.json")
    pyright_config: dict[str, object] = json.loads(pyright_config_text)

    assert pyright_config["include"] == ["app", "main.py"]
    assert pyright_config["extraPaths"] == ["../../packages/shared-python"]
    assert "**/__tests__" in pyright_config["exclude"]  # type: ignore[operator]
    assert "venvPath" not in pyright_config
    assert "venv" not in pyright_config


def test_public_ci_typecheck_targets_selected_api_entrypoints() -> None:
    ci_workflow_text: str = read_text(".github/workflows/ci.yml")

    for relative_path in (
        "app/api/v1/routes/retrieval.py",
        "app/api/v1/routes/qstash_callbacks.py",
        "app/api/v1/routes/documents.py",
        "app/api/v1/routes/api_key.py",
        "app/core/dependencies.py",
        "app/api/api_router.py",
    ):
        assert relative_path in ci_workflow_text, relative_path


def test_publication_guard_scan_blocks_private_cloud_identifiers() -> None:
    for description, pattern in PUBLICATION_SCAN_PATTERNS:
        assert not find_publication_pattern_matches(pattern), description


def test_public_workflows_do_not_persist_checkout_credentials() -> None:
    for relative_path in (
        ".github/workflows/build-images.yml",
        ".github/workflows/ci.yml",
    ):
        workflow_text: str = read_text(relative_path)
        checkout_step_count: int = workflow_text.count("uses: actions/checkout@v4")

        assert checkout_step_count > 0, relative_path
        assert (
            workflow_text.count("persist-credentials: false") == checkout_step_count
        ), relative_path


def test_public_ci_workflow_uses_explicit_read_only_token_permissions() -> None:
    ci_workflow_text: str = read_text(".github/workflows/ci.yml")

    assert "permissions:" in ci_workflow_text
    assert "contents: read" in ci_workflow_text


def test_selected_retained_test_surfaces_avoid_private_callback_hosts() -> None:
    retained_test_text: str = read_text(
        "apps/api/__tests__/unit/test_qstash_callbacks.py"
    )
    auth_dependencies_test_text: str = read_text(
        "apps/api/__tests__/unit/test_auth_dependencies.py"
    )
    api_key_service_test_text: str = read_text(
        "apps/api/__tests__/unit/test_api_key_service.py"
    )
    system_level_dependencies_test_text: str = read_text(
        "apps/api/__tests__/unit/rate_limit/test_system_level_dependencies.py"
    )
    mcp_query_test_text: str = read_text(
        "apps/api/__tests__/unit/test_mcp_query_tool.py"
    )
    openai_timeout_test_text: str = read_text(
        "packages/shared-python/shared/tests/test_openai_timeout_defaults.py"
    )
    guest_registration_test_text: str = read_text(
        "apps/api/__tests__/unit/test_guest_registration_service.py"
    )
    mineru_quota_test_text: str = read_text(
        "apps/worker/tests/services/test_mineru_quota_manager.py"
    )
    ali_quota_test_text: str = read_text(
        "apps/worker/tests/services/test_ali_quota_manager.py"
    )

    assert "api.internal" not in retained_test_text
    assert "workers.dev" not in retained_test_text
    assert "wangbinqi" not in retained_test_text
    assert "job_af999f445be6" not in retained_test_text
    assert (
        "msg_SsSaiS4nUd1vhMifwgiRxyLsvKwQpyiTbotjmvhgmnKYCsdHnYL9b4DQ28WN8euniUHdZYYufg1FMF4sRjuNRPTHhRBbvTA"
        not in retained_test_text
    )
    assert "sk_guest_jobs" not in auth_dependencies_test_text
    assert "sk_guest_billing_credits" not in auth_dependencies_test_text
    assert "sk_guest_billing" not in auth_dependencies_test_text
    assert "sk_guest_extended" not in auth_dependencies_test_text
    assert "sk_test_token" not in api_key_service_test_text
    assert "sk_test_guest" not in api_key_service_test_text
    assert "sk_guest" not in system_level_dependencies_test_text
    assert "sk_test_123" not in system_level_dependencies_test_text
    assert "sk_revalidate_token" not in system_level_dependencies_test_text
    assert "api-staging.knowhereto.ai" not in mcp_query_test_text
    assert "sk-explicit" not in openai_timeout_test_text
    assert "dummy-openai-key-for-tests" not in openai_timeout_test_text
    assert "codex-staging-smoke-20260406" not in guest_registration_test_text
    assert "codex-guest-registration-smoke" not in guest_registration_test_text
    assert "codex-smoke" not in guest_registration_test_text
    assert "codex-test" not in mcp_query_test_text
    assert "sk-1" not in mineru_quota_test_text
    assert "sk-2" not in mineru_quota_test_text
    assert "sk-primary" not in mineru_quota_test_text
    assert "sk-backup" not in mineru_quota_test_text
    assert "sk-ali-1" not in ali_quota_test_text
    assert "sk-ali-2" not in ali_quota_test_text
    assert "sk-abc" not in ali_quota_test_text
    assert "sk-def" not in ali_quota_test_text
    assert "sk-ghi" not in ali_quota_test_text
    assert "sk-1" not in ali_quota_test_text
    assert "sk-2" not in ali_quota_test_text


def test_selected_retained_fixtures_avoid_personal_contact_strings() -> None:
    for relative_path in (
        "apps/worker/tests/fixtures/full.md",
        "apps/worker/tests/fixtures/full_notoc.md",
    ):
        fixture_text: str = read_text(relative_path)
        assert "764796421@qq.c0m" not in fixture_text
        assert "@qq.com" not in fixture_text
        assert "@163.com" not in fixture_text
        assert "@gmail.com" not in fixture_text
        assert "@outlook.com" not in fixture_text


def test_selected_runtime_text_surfaces_remove_internal_planning_refs() -> None:
    prompt_service_text: str = read_text(
        "packages/shared-python/shared/services/ai/prompt_service.py"
    )
    kb_utils_text: str = read_text("apps/worker/app/services/common/kb_utils.py")

    assert "hierarchy_llm_compact_input_0c446abf.plan.md" not in prompt_service_text
    assert "build_prompt 调用" not in prompt_service_text
    assert "process_llm_history 完成" not in prompt_service_text
    assert "Atlas number (图集号)" not in prompt_service_text
    assert "Atlas name (图集名)" not in prompt_service_text
    assert "Page label (页码)" not in prompt_service_text
    assert " 包括 " not in kb_utils_text


def test_public_self_hosting_docs_cover_published_ghcr_images() -> None:
    self_hosting_text: str = read_text("docs/self-hosting.md")
    release_distribution_text: str = read_text("docs/release-distribution.md")

    assert "docker pull ghcr.io/ontos-ai/knowhere-backend" in self_hosting_text
    assert "docker pull ghcr.io/ontos-ai/knowhere-worker" in self_hosting_text
    assert "--env-file apps/api/.env" in self_hosting_text
    assert "--env-file apps/worker/.env" in self_hosting_text
    assert "docker run" in self_hosting_text
    assert "ghcr.io/ontos-ai/knowhere-backend" in release_distribution_text
    assert "ghcr.io/ontos-ai/knowhere-worker" in release_distribution_text


def test_public_repo_omits_unvetted_smoke_test_suites() -> None:
    for relative_path in (
        "apps/api/__tests__/smoke/test_qstash_callbacks_api.py",
        "apps/api/__tests__/smoke/test_webhook_creation.py",
        "apps/api/__tests__/smoke/test_webhook_secrets_api.py",
        "apps/worker/tests/smoke/test_webhook_dispatch.py",
    ):
        assert not (REPO_ROOT / relative_path).exists(), relative_path

    fakes_text: str = read_text("packages/shared-python/shared/tests/fakes.py")
    assert "For smoke tests" not in fakes_text
    assert "smoke tests specifically" not in fakes_text


def test_worker_tests_do_not_keep_stale_runtime_artifacts() -> None:
    assert not (REPO_ROOT / "apps/worker/tests/.tmp_layout_parser").exists()


def main() -> None:
    test_publication_foundation_files_exist()
    test_license_and_notice_match_apache_2_baseline()
    test_root_pyproject_exposes_python_workspace_members()
    test_gitignore_blocks_agent_artifacts_from_reappearing()
    test_private_root_only_files_are_removed_from_publication_branch()
    test_readme_links_public_foundation_documents()
    test_build_images_workflow_only_targets_ghcr()
    test_build_images_workflow_keeps_pr_permissions_read_only()
    test_repo_surface_is_python_first()
    test_public_docs_cover_services_release_and_local_verification()
    test_local_dev_bootstrap_docs_and_scripts_use_non_secret_demo_api_key()
    test_public_env_examples_and_selected_dev_assets_are_english_first()
    test_selected_shared_redis_and_storage_services_are_english_first()
    test_selected_api_and_shared_runtime_modules_are_english_first()
    test_active_alembic_assets_and_local_init_files_are_public_safe()
    test_selected_active_api_text_surfaces_are_english_first()
    test_selected_shared_python_public_surfaces_are_english_first()
    test_selected_api_support_surfaces_are_english_first()
    test_selected_module_support_surfaces_are_english_first()
    test_selected_state_and_model_support_surfaces_are_english_first()
    test_selected_files_only_keep_english_comments_and_docstrings()
    test_selected_repository_files_only_keep_english_comments_and_docstrings()
    test_selected_large_repository_and_service_files_only_keep_english_comments_and_docstrings()
    test_selected_small_modules_only_keep_english_comments_and_docstrings()
    test_selected_utility_files_only_keep_english_comments_and_docstrings()
    test_selected_redis_support_files_only_keep_english_comments_and_docstrings()
    test_selected_redis_core_files_only_keep_english_comments_and_docstrings()
    test_selected_storage_support_files_only_keep_english_comments_and_docstrings()
    test_storage_upload_service_only_keeps_english_comments_and_docstrings()
    test_selected_worker_parser_files_only_keep_english_comments_and_docstrings()
    test_remaining_support_files_only_keep_english_comments_and_docstrings()
    test_stripe_service_only_keeps_english_comments_and_docstrings()
    test_workspace_pyprojects_use_uv_workspace_sources()
    test_readme_documents_inline_quality_commands()
    test_public_ci_workflow_uses_inline_quality_commands()
    test_public_api_typecheck_baseline_targets_runtime_surface_only()
    test_public_ci_typecheck_targets_selected_api_entrypoints()
    test_publication_guard_scan_blocks_private_cloud_identifiers()
    test_public_workflows_do_not_persist_checkout_credentials()
    test_public_ci_workflow_uses_explicit_read_only_token_permissions()
    test_selected_retained_test_surfaces_avoid_private_callback_hosts()
    test_selected_retained_fixtures_avoid_personal_contact_strings()
    test_selected_runtime_text_surfaces_remove_internal_planning_refs()
    test_public_self_hosting_docs_cover_published_ghcr_images()
    test_public_repo_omits_unvetted_smoke_test_suites()
    test_worker_tests_do_not_keep_stale_runtime_artifacts()


if __name__ == "__main__":
    main()
