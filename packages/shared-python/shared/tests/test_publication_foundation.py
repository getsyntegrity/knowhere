from __future__ import annotations

from pathlib import Path
import tomllib


REPO_ROOT: Path = Path(__file__).resolve().parents[4]


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


def main() -> None:
    test_publication_foundation_files_exist()
    test_license_and_notice_match_apache_2_baseline()
    test_root_pyproject_exposes_python_workspace_members()
    test_gitignore_blocks_agent_artifacts_from_reappearing()
    test_private_root_only_files_are_removed_from_publication_branch()
    test_readme_links_public_foundation_documents()
    test_build_images_workflow_only_targets_ghcr()


if __name__ == "__main__":
    main()
