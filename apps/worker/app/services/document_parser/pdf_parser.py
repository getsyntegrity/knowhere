import importlib
import os
from typing import Any, cast

from loguru import logger

from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.mineru_pdf_service import parse_pdf_via_mineru


def upload_and_parse(pdf_url: str, filename: str, output_dir: str, s3_key: str | None = None) -> None:
    """Compatibility wrapper for the extracted MinerU workflow module."""
    parse_pdf_via_mineru(pdf_url, filename, output_dir, s3_key=s3_key)


def parse_pdfs(pdf_path, filename, output_dir, base_llm_paras, profile=None, relative_root=None, s3_key=None):
    route = profile.route if profile else "standard"

    if route == "fast":
        logger.info(f"⚡ Fast path: extracting with pymupdf4llm for {filename}")
        pymupdf4llm = cast(Any, importlib.import_module("pymupdf4llm"))

        os.makedirs(output_dir, exist_ok=True)
        image_dir = os.path.join(output_dir, "images")
        os.makedirs(image_dir, exist_ok=True)

        md_text = pymupdf4llm.to_markdown(
            pdf_path,
            write_images=True,
            image_path=image_dir,
            image_format="png",
        )

        full_md_path = os.path.join(output_dir, "full.md")
        with open(full_md_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(md_text)

        img_count = len([name for name in os.listdir(image_dir) if name.endswith(".png")])
        logger.info(
            f"⚡ Fast path: wrote {len(md_text)} chars to full.md, {img_count} images extracted"
        )
    else:
        upload_and_parse(pdf_path, filename, output_dir, s3_key=s3_key)

    logger.info("✅ PDF parsing step 1 complete: text extracted")

    base_llm_paras.update({"doc_name": filename})
    return parse_md(
        output_dir,
        source_type="md",
        file_path=os.path.join(output_dir, "full.md"),
        base_llm_paras=base_llm_paras,
        relative_root=relative_root,
    )
