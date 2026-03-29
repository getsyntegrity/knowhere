from pathlib import Path

from app.services.document_parser import image_parser


def test_local_image_to_data_url_keeps_small_files_on_disk(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "small.png"
    image_path.write_bytes(b"tiny")

    data_url = image_parser.local_image_to_data_url(
        image_path,
        cut=True,
        min_size=10,
        max_size=1024,
    )

    assert data_url is None
    assert image_path.exists()
