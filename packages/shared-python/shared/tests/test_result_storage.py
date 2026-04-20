from pathlib import Path

import pytest


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

    uploads: list[tuple[str, str, str]] = []

    def fake_upload_to_s3(local_path, storage_key, bucket):
        uploads.append((Path(local_path).name, storage_key, bucket))

    monkeypatch.setattr(
        "shared.services.storage.result_storage.upload_to_s3",
        fake_upload_to_s3,
    )

    bundle = ResultS3(results_bucket="results-bucket").upload(
        job_id="job_123",
        result_dir=str(result_dir),
        temp_dir=str(tmp_path),
    )

    assert bundle.zip_key == "results/job_123.zip"
    assert bundle.raw_prefix == "results/job_123/"
    assert bundle.raw_files == {
        "full.md": "results/job_123/full.md",
        "images/page-1.png": "results/job_123/images/page-1.png",
        "tables/table-1.html": "results/job_123/tables/table-1.html",
    }
    assert ("result_job_123.zip", "results/job_123.zip", "results-bucket") in uploads
    assert ("page-1.png", "results/job_123/images/page-1.png", "results-bucket") in uploads
    assert ("table-1.html", "results/job_123/tables/table-1.html", "results-bucket") in uploads
    assert all(".DS_Store" not in upload[1] for upload in uploads)
    assert all("/tmp/" not in upload[1] for upload in uploads)
    assert not (tmp_path / "result_job_123.zip").exists()


def test_result_s3_generate_artifact_url_delegates_key_construction(monkeypatch):
    from shared.services.storage.result_storage import ResultS3

    generated = {}

    def fake_generate_download_url(storage_key, bucket=None, expires_in=3600):
        generated.update(
            {
                "storage_key": storage_key,
                "bucket": bucket,
                "expires_in": expires_in,
            }
        )
        return {"download_url": f"https://assets.test/{storage_key}", "expires_in": expires_in}

    monkeypatch.setattr(
        "shared.services.storage.result_storage.generate_download_url",
        fake_generate_download_url,
    )

    url = ResultS3(results_bucket="results-bucket").generate_artifact_url(
        job_id="job_123",
        artifact_ref="images/page-1.png",
        expires_in=600,
    )

    assert url == "https://assets.test/results/job_123/images/page-1.png"
    assert generated == {
        "storage_key": "results/job_123/images/page-1.png",
        "bucket": "results-bucket",
        "expires_in": 600,
    }


def test_result_s3_normalizes_only_client_artifact_refs():
    from shared.services.storage.result_storage import ResultS3

    storage = ResultS3(results_bucket="results-bucket")

    assert storage.normalize_artifact_ref("/images/page-1.png") == "images/page-1.png"
    assert storage.normalize_artifact_ref("tables/table-1.html") == "tables/table-1.html"
    assert storage.normalize_artifact_ref("full.md") is None
    assert storage.normalize_artifact_ref("../images/page-1.png") == "images/page-1.png"
