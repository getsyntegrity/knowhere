import pytest
import pandas as pd
from PIL import Image

from shared.core.exceptions.domain_exceptions import StorageServiceException
from shared.services.redis.chunks_redis_service import ChunksRedisService
from shared.services.storage.zip_result_service import ZipResultService


def test_dataframe_to_chunks_preserves_embedded_atlas_image_filename():
    df = pd.DataFrame(
        [
            {
                "content": "[images/05SG522 （总说明）page 4.jpg]\n[page-4] 05SG522 （总说明）page 4\n",
                "path": "05SG522 （总说明）page 4",
                "type": "image",
                "length": 42,
                "keywords": "",
                "summary": "",
                "know_id": "atlas-page-4",
                "tokens": "",
                "connectto": "",
                "addtime": "2026-04-13T00:00:00Z",
                "page_nums": "4",
            }
        ]
    )

    chunks = ChunksRedisService(None)._dataframe_to_chunks(df)

    assert chunks[0]["metadata"]["file_path"] == "images/05SG522 （总说明）page 4.jpg"


def test_collect_image_files_uses_metadata_file_path_for_atlas_images(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    wrong_path = images_dir / "wrong-first.jpg"
    correct_path = images_dir / "05SG522 （总说明）page 4.jpg"
    Image.new("RGB", (8, 8), color="red").save(wrong_path)
    Image.new("RGB", (8, 8), color="blue").save(correct_path)

    monkeypatch.setattr(
        "os.listdir",
        lambda _: ["wrong-first.jpg", "05SG522 （总说明）page 4.jpg"],
    )

    image_files = ZipResultService()._collect_image_files(
        [
            {
                "chunk_id": "atlas-page-4",
                "type": "image",
                "path": "05SG522 （总说明）page 4",
                "metadata": {
                    "file_path": "images/05SG522 （总说明）page 4.jpg",
                    "original_name": "05SG522 （总说明）page 4.jpg",
                },
            }
        ],
        str(images_dir),
    )

    assert image_files[0]["source_path"] == str(correct_path)


def test_collect_image_files_raises_when_declared_image_is_missing(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    wrong_path = images_dir / "wrong-first.jpg"
    Image.new("RGB", (8, 8), color="red").save(wrong_path)

    monkeypatch.setattr("os.listdir", lambda _: ["wrong-first.jpg"])

    with pytest.raises(StorageServiceException, match="Cannot resolve image file"):
        ZipResultService()._collect_image_files(
            [
                {
                    "chunk_id": "atlas-page-4",
                    "type": "image",
                    "path": "05SG522 （总说明）page 4",
                    "metadata": {
                        "file_path": "images/05SG522 （总说明）page 4.jpg",
                        "original_name": "05SG522 （总说明）page 4.jpg",
                    },
                }
            ],
            str(images_dir),
        )


def test_collect_table_files_raises_when_declared_table_is_missing(tmp_path, monkeypatch):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    wrong_path = tables_dir / "wrong-first.html"
    wrong_path.write_text("<table><tr><td>wrong</td></tr></table>", encoding="utf-8")

    monkeypatch.setattr("os.listdir", lambda _: ["wrong-first.html"])

    with pytest.raises(StorageServiceException, match="Cannot resolve table file"):
        ZipResultService()._collect_table_files(
            [
                {
                    "chunk_id": "table-1",
                    "type": "table",
                    "path": "05SG522 表1",
                    "metadata": {
                        "file_path": "tables/05SG522 表1.html",
                        "original_name": "05SG522 表1.html",
                    },
                }
            ],
            str(tables_dir),
        )
