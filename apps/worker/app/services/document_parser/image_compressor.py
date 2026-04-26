# pyright: reportAttributeAccessIssue=false
"""
Unified output image compressor.

Called BEFORE ZIP packaging to ensure all images in the output directory
are within reasonable size/dimension limits for downstream consumption.

Design decisions:
- PNG with alpha channel (transparency) are kept as PNG — these are typically
  formula renderings from MinerU where lossless + transparency matters.
- PNG without alpha (opaque) are converted to JPEG — these are typically
  page renders, photos, screenshots where JPEG is more efficient.
- JPEG files above the max dimension are resized.
- Very small images (< 50KB) are skipped to avoid degrading icons/logos.
- Extremely large images (dimensions > max_side) are resized with LANCZOS.
"""

import os
from typing import NamedTuple

from loguru import logger

# ── Configuration ─────────────────────────────────────────────────────
OUTPUT_MAX_SIDE = 2400  # max pixels on longest side
OUTPUT_JPEG_QUALITY = 85  # JPEG quality (85 is visually lossless)
SKIP_BELOW_BYTES = 50_000  # skip images smaller than 50KB
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


class CompressionStats(NamedTuple):
    """Summary of a compress_output_images run."""

    processed: int
    skipped: int
    converted_png_to_jpg: int
    resized: int
    bytes_before: int
    bytes_after: int
    rename_map: dict  # {"old_relative_path": "new_relative_path"}, e.g. {"images/foo.png": "images/foo.jpg"}


def _has_transparency(img) -> bool:
    """Check whether a PIL Image has meaningful alpha (transparency) data."""
    if img.mode != "RGBA":
        return False
    # Sample alpha channel — if any pixel has alpha < 250, treat as transparent
    alpha = img.getchannel("A")
    extrema = alpha.getextrema()
    return extrema[0] < 250


def compress_output_images(
    output_dir: str,
    *,
    max_side: int = OUTPUT_MAX_SIDE,
    jpeg_quality: int = OUTPUT_JPEG_QUALITY,
    skip_below_bytes: int = SKIP_BELOW_BYTES,
) -> CompressionStats:
    """
    Compress all images under ``output_dir/images/`` in-place.

    - Opaque PNGs → JPEG (significant size reduction)
    - Large dimensions → resize to max_side
    - Transparent PNGs → keep as PNG but resize if oversized
    - JPEG/WebP → resize if oversized, re-encode if quality can be reduced

    Returns a CompressionStats summary (includes rename_map for updating
    DataFrame references when PNG→JPG conversions occurred).
    """
    from PIL import Image

    images_dir = os.path.join(output_dir, "images")
    if not os.path.isdir(images_dir):
        return CompressionStats(0, 0, 0, 0, 0, 0, {})

    processed = 0
    skipped = 0
    converted = 0
    resized_count = 0
    total_before = 0
    total_after = 0
    rename_map = {}  # old_relative_path → new_relative_path

    for filename in os.listdir(images_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTS:
            continue

        file_path = os.path.join(images_dir, filename)
        if not os.path.isfile(file_path):
            continue

        file_size = os.path.getsize(file_path)
        total_before += file_size

        # Skip tiny images (icons, logos, decorations)
        if file_size < skip_below_bytes:
            skipped += 1
            total_after += file_size
            continue

        try:
            img = Image.open(file_path)
            w, h = img.size
            needs_resize = max(w, h) > max_side
            is_png = ext == ".png"
            has_alpha = is_png and _has_transparency(img)

            if is_png and not has_alpha:
                # Opaque PNG → convert to JPEG
                if needs_resize:
                    ratio = max_side / max(w, h)
                    new_w, new_h = int(w * ratio), int(h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    resized_count += 1

                # Convert RGBA → RGB for JPEG
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")

                jpg_path = os.path.splitext(file_path)[0] + ".jpg"
                img.save(jpg_path, "JPEG", quality=jpeg_quality, optimize=True)
                img.close()

                # Remove original PNG
                if jpg_path != file_path:
                    os.remove(file_path)
                    # Record rename for downstream reference updates
                    old_rel = f"images/{filename}"
                    new_rel = f"images/{os.path.basename(jpg_path)}"
                    rename_map[old_rel] = new_rel

                converted += 1
                processed += 1
                total_after += os.path.getsize(jpg_path)

            elif is_png and has_alpha:
                # Transparent PNG → keep as PNG but resize if needed
                if needs_resize:
                    ratio = max_side / max(w, h)
                    new_w, new_h = int(w * ratio), int(h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    img.save(file_path, "PNG", optimize=True)
                    resized_count += 1
                    processed += 1
                else:
                    skipped += 1
                img.close()
                total_after += os.path.getsize(file_path)

            else:
                # JPEG / WebP — only resize if dimension exceeds limit
                if needs_resize:
                    ratio = max_side / max(w, h)
                    new_w, new_h = int(w * ratio), int(h * ratio)
                    img = img.resize((new_w, new_h), Image.LANCZOS)

                    if ext in (".jpg", ".jpeg"):
                        if img.mode in ("RGBA", "P", "LA"):
                            img = img.convert("RGB")
                        img.save(file_path, "JPEG", quality=jpeg_quality, optimize=True)
                    elif ext == ".webp":
                        img.save(file_path, "WebP", quality=jpeg_quality)

                    resized_count += 1
                    processed += 1
                else:
                    skipped += 1
                img.close()
                total_after += os.path.getsize(file_path)

        except Exception as exc:
            logger.warning(f"[image_compressor] Failed to process {filename}: {exc}")
            skipped += 1
            total_after += file_size

    stats = CompressionStats(
        processed=processed,
        skipped=skipped,
        converted_png_to_jpg=converted,
        resized=resized_count,
        bytes_before=total_before,
        bytes_after=total_after,
        rename_map=rename_map,
    )

    if processed > 0:
        ratio = total_before / total_after if total_after > 0 else 0
        logger.info(
            f"[image_compressor] Compressed {processed} images "
            f"({converted} PNG→JPG, {resized_count} resized), "
            f"skipped {skipped}. "
            f"Size: {total_before / 1024 / 1024:.1f}MB → {total_after / 1024 / 1024:.1f}MB "
            f"({ratio:.1f}x reduction)"
        )

    return stats


def apply_rename_map_to_dataframe(df, rename_map: dict):
    """
    Update image path references in the parsed DataFrame after PNG→JPG conversion.

    The DataFrame's 'path' column contains relative paths like 'images/foo.png'.
    When the compressor converts foo.png → foo.jpg, references must be updated
    so the ZIP packager can find the correct files.

    Args:
        df: pandas DataFrame with columns matching settings.ALL_DF_COLS
        rename_map: {old_relative_path: new_relative_path} from CompressionStats
    """
    if not rename_map or df is None or df.empty:
        return df

    # The 'path' column (index 1 in ALL_DF_COLS) stores the relative path
    path_col = df.columns[1] if len(df.columns) > 1 else "path"
    if path_col not in df.columns:
        return df

    updated = 0
    for old_path, new_path in rename_map.items():
        mask = df[path_col] == old_path
        if mask.any():
            df.loc[mask, path_col] = new_path
            updated += mask.sum()

    if updated > 0:
        logger.info(
            f"[image_compressor] Updated {updated} image path references in DataFrame"
        )

    return df
