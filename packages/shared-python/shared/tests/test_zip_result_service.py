from pathlib import Path

import pytest

from shared.core.exceptions.domain_exceptions import StorageServiceException
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


def test_generate_zip_package_raises_for_image_chunk_without_packaged_image(
    tmp_path: Path,
) -> None:
    add_dir: Path = tmp_path / "parsed"
    add_dir.mkdir()
    images_dir: Path = add_dir / "images"
    images_dir.mkdir()
    (images_dir / "wrong-first.jpg").write_text(
        "not the declared image", encoding="utf-8"
    )

    zip_service = ZipResultService()

    with pytest.raises(StorageServiceException, match="Cannot resolve image file"):
        zip_service.generate_zip_package(
            job_id="job-missing-image",
            chunks=_build_missing_image_chunk(),
            add_dir=str(add_dir),
            source_file_name="source.pdf",
            data_id=None,
            job_metadata={},
            temp_dir=str(tmp_path),
        )


def test_generate_zip_package_raises_when_image_directory_is_missing(
    tmp_path: Path,
) -> None:
    add_dir: Path = tmp_path / "parsed"
    add_dir.mkdir()

    zip_service = ZipResultService()

    with pytest.raises(StorageServiceException, match="Image directory not found"):
        zip_service.generate_zip_package(
            job_id="job-missing-image-dir",
            chunks=_build_missing_image_chunk(),
            add_dir=str(add_dir),
            source_file_name="source.pdf",
            data_id=None,
            job_metadata={},
            temp_dir=str(tmp_path),
        )
