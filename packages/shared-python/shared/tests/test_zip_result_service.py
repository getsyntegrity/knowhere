import json
import zipfile
from pathlib import Path

from shared.services.storage.zip_result_service import ZipResultService


def test_generate_zip_package_omits_file_path_for_image_chunk_without_packaged_image(
    tmp_path: Path,
) -> None:
    add_dir: Path = tmp_path / "parsed"
    add_dir.mkdir()

    chunks: list[dict[str, object]] = [
        {
            "chunk_id": "1ea57a7f-bf8d-5188-9969-35ad3e2dd655",
            "type": "image",
            "content": "image content",
            "path": "Default_Root/example.png/违规公款消费处分规定.png",
            "metadata": {
                "file_path": "images/违规公款消费处分规定.png",
                "summary": "summary",
                "length": 13,
                "page_nums": [],
            },
        }
    ]

    zip_service = ZipResultService()

    zip_file_path, _, _, _ = zip_service.generate_zip_package(
        job_id="job-missing-image",
        chunks=chunks,
        add_dir=str(add_dir),
        source_file_name="source.pdf",
        data_id=None,
        job_metadata={},
        temp_dir=str(tmp_path),
    )

    with zipfile.ZipFile(zip_file_path) as zip_file:
        zip_names: list[str] = zip_file.namelist()
        formatted_chunks: list[dict[str, object]] = json.loads(zip_file.read("chunks.json"))["chunks"]

    assert all(not zip_name.startswith("images/") for zip_name in zip_names)
    assert formatted_chunks[0]["type"] == "image"
    assert "file_path" not in formatted_chunks[0]["metadata"]
