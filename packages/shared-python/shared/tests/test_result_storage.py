from pathlib import Path

import pytest


def test_result_storage_does_not_depend_on_app_package():
    source_path = Path(__file__).parents[1] / "services" / "storage" / "result_storage.py"
    source = source_path.read_text(encoding="utf-8")

    assert "app.services" not in source


def test_result_s3_upload_publishes_zip_and_raw_result_tree(monkeypatch, tmp_path):
    from shared.services.storage.result_storage import ResultS3

    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "full.md").write_text("body", encoding="utf-8")
    (result_dir / "images").mkdir()
    (result_dir / "images" / "page-1.png").write_bytes(b"png")
    (result_dir / "tables").mkdir()
    (result_dir / "tables" / "table-1.html").write_text("<table></table>", encoding="utf-8")
    (result_dir / ".DS_Store").write_bytes(b"ignored")
    (result_dir / "tmp").mkdir()
    (result_dir / "tmp" / "scratch.txt").write_text("ignored", encoding="utf-8")

    class FakeStorageAdapter:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str, str]] = []

        def upload_file(self, local_path, storage_key, bucket=None):
            self.uploads.append((Path(local_path).name, storage_key, bucket))
            return {"status": "success"}

    zip_path = tmp_path / "canonical.zip"
    zip_path.write_bytes(b"canonical-zip")
    adapter = FakeStorageAdapter()

    bundle = ResultS3(results_bucket="results-bucket", storage_adapter=adapter).upload(
        job_id="job_123",
        result_dir=str(result_dir),
        zip_file_path=str(zip_path),
    )

    assert bundle.zip_key == "results/job_123.zip"
    assert bundle.raw_prefix == "results/job_123/"
    assert bundle.raw_files == {
        "full.md": "results/job_123/full.md",
        "images/page-1.png": "results/job_123/images/page-1.png",
        "tables/table-1.html": "results/job_123/tables/table-1.html",
    }
    assert ("canonical.zip", "results/job_123.zip", "results-bucket") in adapter.uploads
    assert ("page-1.png", "results/job_123/images/page-1.png", "results-bucket") in adapter.uploads
    assert ("table-1.html", "results/job_123/tables/table-1.html", "results-bucket") in adapter.uploads
    assert all(".DS_Store" not in upload[1] for upload in adapter.uploads)
    assert all("/tmp/" not in upload[1] for upload in adapter.uploads)
    assert not zip_path.exists()


def test_result_s3_generate_artifact_url_delegates_key_construction():
    from shared.services.storage.result_storage import ResultS3

    class FakeStorageAdapter:
        def __init__(self) -> None:
            self.generated = {}

        def generate_presigned_url(self, storage_key, expiration=3600, bucket=None, method="GET"):
            self.generated.update(
                {
                    "storage_key": storage_key,
                    "bucket": bucket,
                    "expires_in": expiration,
                    "method": method,
                }
            )
            return f"https://assets.test/{storage_key}"

    adapter = FakeStorageAdapter()

    url = ResultS3(results_bucket="results-bucket", storage_adapter=adapter).generate_artifact_url(
        job_id="job_123",
        artifact_ref="images/page-1.png",
        expires_in=600,
    )

    assert url == "https://assets.test/results/job_123/images/page-1.png"
    assert adapter.generated == {
        "storage_key": "results/job_123/images/page-1.png",
        "bucket": "results-bucket",
        "expires_in": 600,
        "method": "GET",
    }


def test_result_s3_normalizes_only_client_artifact_refs():
    from shared.services.storage.result_storage import ResultS3

    storage = ResultS3(results_bucket="results-bucket")

    assert storage.normalize_artifact_ref("/images/page-1.png") == "images/page-1.png"
    assert storage.normalize_artifact_ref("tables/table-1.html") == "tables/table-1.html"
    assert storage.normalize_artifact_ref("full.md") is None
    assert storage.normalize_artifact_ref("../images/page-1.png") == "images/page-1.png"
