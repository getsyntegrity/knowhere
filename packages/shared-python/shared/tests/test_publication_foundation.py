from __future__ import annotations

from pathlib import Path
import json
import re
import tomllib


REPO_ROOT: Path = Path(__file__).resolve().parents[4]
CHINESE_TEXT_PATTERN: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff]")


def read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


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


def test_repo_surface_is_python_first() -> None:
    readme_text: str = read_text("README.md")

    for removed_path in (
        "package.json",
        "pnpm-workspace.yaml",
        "pnpm-lock.yaml",
        "turbo.json",
        "packages/openapi-specs",
        "packages/shared-types",
    ):
        assert not (REPO_ROOT / removed_path).exists(), removed_path

    for required_path in (
        "scripts/check-public.sh",
        "scripts/test-public.sh",
        "scripts/test-public-shared.sh",
        "scripts/test-public-api.sh",
        "scripts/test-public-worker.sh",
        "scripts/typecheck-public.sh",
        ".github/workflows/ci.yml",
    ):
        assert (REPO_ROOT / required_path).exists(), required_path

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
        assert "Optional integrations" in env_text
        assert "DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere" in env_text
        assert "S3_ENDPOINT_URL=http://localhost:4566" in env_text
        assert "S3_ACCESS_KEY_ID=test" in env_text
        assert "S3_SECRET_ACCESS_KEY=test" in env_text
        assert "QSTASH_CALLBACK_BASE_URL=https://api.example.com/api/v1" in env_text
        assert "DEFAULT_FOLDERS=Supplementary_Files,Temporary_Files,templates,images,fragments" in env_text

    assert "知识库" not in api_env_text
    assert "复制此文件" not in api_env_text
    assert "知识库" not in worker_env_text
    assert "复制此文件" not in worker_env_text


def test_workspace_pyprojects_use_uv_workspace_sources() -> None:
    api_pyproject_text: str = read_text("apps/api/pyproject.toml")
    worker_pyproject_text: str = read_text("apps/worker/pyproject.toml")

    assert "knowhere-shared = { workspace = true }" in api_pyproject_text
    assert "knowhere-shared = { workspace = true }" in worker_pyproject_text
    assert 'path = "../../packages/shared-python"' not in api_pyproject_text
    assert 'path = "../../packages/shared-python"' not in worker_pyproject_text


def test_public_scripts_pin_python_3_11_for_uv_commands() -> None:
    for relative_path in (
        "scripts/typecheck-public.sh",
        "scripts/test-public-shared.sh",
        "scripts/test-public-api.sh",
        "scripts/test-public-worker.sh",
    ):
        script_text: str = read_text(relative_path)
        assert "--python 3.11" in script_text, relative_path


def test_public_api_typecheck_baseline_targets_runtime_surface_only() -> None:
    pyright_config_text: str = read_text("apps/api/pyrightconfig.json")
    pyright_config: dict[str, object] = json.loads(pyright_config_text)

    assert pyright_config["include"] == ["app", "main.py"]
    assert pyright_config["extraPaths"] == ["../../packages/shared-python"]
    assert "**/__tests__" in pyright_config["exclude"]  # type: ignore[operator]
    assert "venvPath" not in pyright_config
    assert "venv" not in pyright_config


def test_public_typecheck_script_targets_selected_api_entrypoints() -> None:
    typecheck_script_text: str = read_text("scripts/typecheck-public.sh")

    for relative_path in (
        "app/api/v1/routes/retrieval.py",
        "app/api/v1/routes/qstash_callbacks.py",
        "app/api/v1/routes/documents.py",
        "app/api/v1/routes/api_key.py",
        "app/core/dependencies.py",
        "app/api/api_router.py",
    ):
        assert relative_path in typecheck_script_text, relative_path


def main() -> None:
    test_publication_foundation_files_exist()
    test_license_and_notice_match_apache_2_baseline()
    test_root_pyproject_exposes_python_workspace_members()
    test_gitignore_blocks_agent_artifacts_from_reappearing()
    test_private_root_only_files_are_removed_from_publication_branch()
    test_readme_links_public_foundation_documents()
    test_build_images_workflow_only_targets_ghcr()
    test_repo_surface_is_python_first()
    test_public_docs_cover_services_release_and_local_verification()
    test_public_env_examples_and_selected_dev_assets_are_english_first()
    test_workspace_pyprojects_use_uv_workspace_sources()
    test_public_scripts_pin_python_3_11_for_uv_commands()
    test_public_api_typecheck_baseline_targets_runtime_surface_only()
    test_public_typecheck_script_targets_selected_api_entrypoints()


if __name__ == "__main__":
    main()
