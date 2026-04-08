"""
Tests for the unified image compressor.

Covers:
- PNG → JPEG conversion (opaque PNG)
- Transparent PNG preservation
- Dimension resizing (max_side enforcement)
- Small image skip threshold
- Rename map generation for DataFrame updates
- apply_rename_map_to_dataframe correctness
"""

import os

import pandas as pd
import pytest
from PIL import Image

from app.services.document_parser.image_compressor import (
    compress_output_images,
    apply_rename_map_to_dataframe,
    CompressionStats,
)


def _make_opaque_png(path: str, width: int = 800, height: int = 600) -> None:
    """Create an opaque PNG with noise (ensures file > 50KB threshold)."""
    import numpy as np
    # Random noise so PNG doesn't compress to near-zero
    arr = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    img.save(path, "PNG")


def _make_transparent_png(path: str, width: int = 400, height: int = 400) -> None:
    """Create a PNG with meaningful transparency (alpha < 250) and noise."""
    import numpy as np
    arr = np.random.randint(0, 256, (height, width, 4), dtype=np.uint8)
    # Set alpha channel to 128 throughout to ensure transparency detection
    arr[:, :, 3] = 128
    img = Image.fromarray(arr, "RGBA")
    img.save(path, "PNG")


def _make_jpeg(path: str, width: int = 800, height: int = 600) -> None:
    """Create a JPEG image with noise (ensures file > 50KB threshold)."""
    import numpy as np
    arr = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    img.save(path, "JPEG", quality=95)


def _make_tiny_png(path: str) -> None:
    """Create a deliberately small PNG (< 50KB threshold)."""
    img = Image.new("RGB", (20, 20), color=(0, 0, 0))
    img.save(path, "PNG")


class TestCompressOutputImages:
    """Tests for compress_output_images function."""

    def test_opaque_png_converted_to_jpeg(self, tmp_path):
        """Opaque PNGs should be converted to JPEG for size reduction."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        png_path = images_dir / "page-1.png"
        _make_opaque_png(str(png_path))

        assert png_path.exists()
        stats = compress_output_images(str(tmp_path))

        # PNG should be gone, replaced by JPG
        assert not png_path.exists()
        jpg_path = images_dir / "page-1.jpg"
        assert jpg_path.exists()

        assert stats.converted_png_to_jpg == 1
        assert stats.processed >= 1
        assert "images/page-1.png" in stats.rename_map
        assert stats.rename_map["images/page-1.png"] == "images/page-1.jpg"

    def test_transparent_png_preserved(self, tmp_path):
        """PNGs with transparency should stay as PNG."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        png_path = images_dir / "formula-1.png"
        _make_transparent_png(str(png_path))

        stats = compress_output_images(str(tmp_path))

        # PNG should still exist (not converted)
        assert png_path.exists()
        jpg_path = images_dir / "formula-1.jpg"
        assert not jpg_path.exists()

        assert stats.converted_png_to_jpg == 0
        assert len(stats.rename_map) == 0

    def test_oversized_jpeg_resized(self, tmp_path):
        """JPEGs exceeding max_side should be resized."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        jpg_path = images_dir / "photo.jpg"
        _make_jpeg(str(jpg_path), width=4000, height=3000)

        original_size = os.path.getsize(str(jpg_path))
        stats = compress_output_images(str(tmp_path), max_side=2400)

        assert stats.resized == 1
        assert stats.processed >= 1

        # Check image was actually resized
        with Image.open(str(jpg_path)) as img:
            w, h = img.size
            assert max(w, h) <= 2400

        # Size should decrease
        assert os.path.getsize(str(jpg_path)) < original_size

    def test_small_images_skipped(self, tmp_path):
        """Images below the size threshold should not be processed."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        tiny_path = images_dir / "icon.png"
        _make_tiny_png(str(tiny_path))

        # Tiny PNG is under 50KB threshold
        assert os.path.getsize(str(tiny_path)) < 50_000

        stats = compress_output_images(str(tmp_path))

        assert stats.skipped >= 1
        assert stats.processed == 0
        # File should still exist, unchanged
        assert tiny_path.exists()

    def test_no_images_dir(self, tmp_path):
        """Should handle missing images/ directory gracefully."""
        stats = compress_output_images(str(tmp_path))

        assert stats.processed == 0
        assert stats.skipped == 0
        assert stats.bytes_before == 0

    def test_multiple_files_mixed(self, tmp_path):
        """Test with a mix of file types and sizes."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        # 1. Large opaque PNG → should convert to JPG
        _make_opaque_png(str(images_dir / "render.png"), 3000, 2000)

        # 2. Small transparent PNG → should be skipped (too small)
        _make_transparent_png(str(images_dir / "alpha.png"), 30, 30)

        # 3. Normal JPEG → should be skipped (under max_side)
        _make_jpeg(str(images_dir / "photo.jpg"), 800, 600)

        stats = compress_output_images(str(tmp_path), max_side=2400)

        # render.png → render.jpg (converted + resized)
        assert not (images_dir / "render.png").exists()
        assert (images_dir / "render.jpg").exists()
        assert (images_dir / "alpha.png").exists()  # preserved (small)
        assert (images_dir / "photo.jpg").exists()   # unchanged

        assert stats.converted_png_to_jpg >= 1

    def test_size_reduction(self, tmp_path):
        """Verify that compression actually reduces total size."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        # Create several opaque PNGs (smaller but still above 50KB threshold)
        for i in range(3):
            _make_opaque_png(str(images_dir / f"page-{i}.png"), 400, 300)

        stats = compress_output_images(str(tmp_path))

        assert stats.bytes_after < stats.bytes_before
        assert stats.converted_png_to_jpg == 3


class TestApplyRenameMapToDataframe:
    """Tests for apply_rename_map_to_dataframe function."""

    def test_updates_path_column(self):
        """Should update matching paths in the DataFrame."""
        df = pd.DataFrame({
            "text": ["content1", "content2", "content3"],
            "path": ["images/page-1.png", "images/page-2.png", "text/section.txt"],
            "type": ["image", "image", "text"],
        })
        rename_map = {
            "images/page-1.png": "images/page-1.jpg",
            "images/page-2.png": "images/page-2.jpg",
        }

        result = apply_rename_map_to_dataframe(df, rename_map)

        assert result["path"].iloc[0] == "images/page-1.jpg"
        assert result["path"].iloc[1] == "images/page-2.jpg"
        assert result["path"].iloc[2] == "text/section.txt"  # unchanged

    def test_empty_rename_map(self):
        """Empty rename_map should return DataFrame unchanged."""
        df = pd.DataFrame({
            "text": ["content"],
            "path": ["images/page-1.png"],
        })
        result = apply_rename_map_to_dataframe(df, {})
        assert result["path"].iloc[0] == "images/page-1.png"

    def test_none_dataframe(self):
        """None DataFrame should be handled gracefully."""
        result = apply_rename_map_to_dataframe(None, {"a": "b"})
        assert result is None

    def test_empty_dataframe(self):
        """Empty DataFrame should be handled gracefully."""
        df = pd.DataFrame(columns=["text", "path"])
        result = apply_rename_map_to_dataframe(df, {"a": "b"})
        assert len(result) == 0
