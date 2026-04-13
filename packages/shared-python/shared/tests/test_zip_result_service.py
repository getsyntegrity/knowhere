import json
import zipfile
from pathlib import Path

from shared.services.storage.zip_result_service import ZipResultService


def _build_missing_image_chunk() -> list[dict[str, object]]:
    return [
        {
            "chunk_id": "1ea57a7f-bf8d-5188-9969-35ad3e2dd655",
            "type": "image",
            "content": "[images/违规公款消费处分规定.png]\nImage Content:\nimage content",
            "path": "Default_Root/example.png/违规公款消费处分规定.png",
            "metadata": {
                "file_path": "images/违规公款消费处分规定.png",
                "summary": "summary",
                "length": 13,
                "page_nums": [],
            },
        }
    ]


def test_generate_zip_package_best_effort_normalizes_missing_packaged_image(
    tmp_path: Path,
) -> None:
    add_dir: Path = tmp_path / "parsed"
    add_dir.mkdir()
    images_dir: Path = add_dir / "images"
    images_dir.mkdir()
    (images_dir / "wrong-first.jpg").write_text("not the declared image", encoding="utf-8")

    zip_service = ZipResultService()

    zip_file_path, _, statistics, _ = zip_service.generate_zip_package(
        job_id="job-missing-image",
        chunks=_build_missing_image_chunk(),
        add_dir=str(add_dir),
        source_file_name="source.pdf",
        data_id=None,
        job_metadata={},
        temp_dir=str(tmp_path),
    )

    with zipfile.ZipFile(zip_file_path) as zip_file:
        zip_names: list[str] = zip_file.namelist()
        formatted_chunks: list[dict[str, object]] = json.loads(zip_file.read("chunks.json"))["chunks"]
        manifest: dict[str, object] = json.loads(zip_file.read("manifest.json"))

    assert all(not zip_name.startswith("images/") for zip_name in zip_names)
    assert formatted_chunks[0]["type"] == "text"
    assert "file_path" not in formatted_chunks[0]["metadata"]
    assert statistics == {
        "total_chunks": 1,
        "text_chunks": 1,
        "image_chunks": 0,
        "table_chunks": 0,
        "total_pages": None,
    }
    assert manifest["statistics"] == statistics


def test_generate_zip_package_best_effort_normalizes_missing_image_directory(
    tmp_path: Path,
) -> None:
    add_dir: Path = tmp_path / "parsed"
    add_dir.mkdir()

    zip_service = ZipResultService()

    zip_file_path, _, statistics, _ = zip_service.generate_zip_package(
        job_id="job-missing-image-dir",
        chunks=_build_missing_image_chunk(),
        add_dir=str(add_dir),
        source_file_name="source.pdf",
        data_id=None,
        job_metadata={},
        temp_dir=str(tmp_path),
    )

    with zipfile.ZipFile(zip_file_path) as zip_file:
        zip_names: list[str] = zip_file.namelist()
        formatted_chunks: list[dict[str, object]] = json.loads(zip_file.read("chunks.json"))["chunks"]
        manifest: dict[str, object] = json.loads(zip_file.read("manifest.json"))

    assert all(not zip_name.startswith("images/") for zip_name in zip_names)
    assert formatted_chunks[0]["type"] == "text"
    assert "file_path" not in formatted_chunks[0]["metadata"]
    assert statistics == {
        "total_chunks": 1,
        "text_chunks": 1,
        "image_chunks": 0,
        "table_chunks": 0,
        "total_pages": None,
    }
    assert manifest["statistics"] == statistics
