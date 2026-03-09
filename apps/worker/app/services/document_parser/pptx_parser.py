import io
import os
import re
import subprocess
import time
import requests
import jwt

from loguru import logger
from shared.core.config import settings
from app.services.common.kb_utils import find_images
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.pdf_parser import parse_pdfs
from shared.utils.CommonHelperSync import load_file_bytes
from shared.utils.file_utils import path_handle
from markitdown import MarkItDown
from pptx import Presentation
from pptx2md import ConversionConfig, convert


# ==================== LibreOffice conversion ====================

def pptx_to_pdf_libreoffice(pptx_path, outdir="."):
    """use LibreOffice to convert PPTX to PDF (local engine, formula rendering may be problematic)"""
    soffice_path = settings.LIBER_OFFICE or "/usr/bin/libreoffice"
    from shared.core.constants import ProcessingConstants
    filter_opts = f"Quality={ProcessingConstants.IMG_QUALITY};ReduceImageResolution=false;UseTaggedPDF=true,ExportNotes=true"
    subprocess.run([
        soffice_path, "--headless",
        "--convert-to", f"pdf:writer_pdf_Export:{filter_opts}",
        pptx_path, "--outdir", outdir
    ], check=True)

    base = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf_path = os.path.join(outdir, base + ".pdf")
    return pdf_path, (base + ".pdf")


# ==================== iLoveAPI conversion ====================

def _iloveapi_token():
    """generate iLoveAPI JWT token (self-signed)"""
    secret_key = settings.ILOVEAPI_SECRET_KEY
    public_key = settings.ILOVEAPI_PUBLIC_KEY
    if not secret_key or not public_key:
        raise ValueError("ILOVEAPI_PUBLIC_KEY and ILOVEAPI_SECRET_KEY must be set in .env")

    now = int(time.time())
    payload = {
        "iss": "user",
        "jti": public_key,
        "iat": now,
        "nbf": now,
        "exp": now + 7200,  # 2 hours
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def pptx_to_pdf_api(pptx_path, outdir="."):
    """
    use iloveapi to convert pptx to pdf (file-path based, used by debug_parse.py)
    API docs: https://www.iloveapi.com/docs/api-reference
    """
    with open(pptx_path, "rb") as f:
        pptx_bytes = f.read()
    filename = os.path.basename(pptx_path)
    pdf_bytes = _pptx_bytes_to_pdf_bytes(pptx_bytes, filename)

    base = os.path.splitext(filename)[0]
    pdf_name = base + ".pdf"
    pdf_path = os.path.join(outdir, pdf_name)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    logger.info(f"[iLoveAPI] PDF saved: {pdf_path} ({len(pdf_bytes) / 1024:.1f} KB)")
    return pdf_path, pdf_name


def _pptx_bytes_to_pdf_bytes(pptx_bytes: bytes, filename: str) -> bytes:
    """
    Convert PPTX bytes → PDF bytes via iLoveAPI. Pure in-memory, no disk I/O.
    """
    token = _iloveapi_token()
    headers = {"Authorization": f"Bearer {token}"}
    base_url = settings.ILOVEAPI_BASE_URL
    timeout = settings.ILOVEAPI_TIMEOUT

    # Step 1: Start task
    logger.info(f"[iLoveAPI] Starting officepdf task for: {filename}")
    res = requests.get(f"{base_url}/start/officepdf", headers=headers, timeout=timeout)
    res.raise_for_status()
    start_data = res.json()
    server = start_data["server"]
    task_id = start_data["task"]
    server_url = f"https://{server}/v1"
    logger.info(f"[iLoveAPI] Task started: {task_id} on {server}")

    # Step 2: Upload from memory (BytesIO, no disk write)
    logger.info(f"[iLoveAPI] Uploading {filename} ({len(pptx_bytes)/1024:.1f} KB)...")
    upload_res = requests.post(
        f"{server_url}/upload",
        headers=headers,
        data={"task": task_id},
        files={"file": (filename, io.BytesIO(pptx_bytes))},
        timeout=timeout,
    )
    upload_res.raise_for_status()
    server_filename = upload_res.json()["server_filename"]
    logger.info(f"[iLoveAPI] Uploaded: {server_filename}")

    # Step 3: Process
    logger.info(f"[iLoveAPI] Processing officepdf...")
    process_res = requests.post(
        f"{server_url}/process",
        headers=headers,
        json={
            "task": task_id,
            "tool": "officepdf",
            "files": [{"server_filename": server_filename, "filename": filename}],
        },
        timeout=timeout,
    )
    process_res.raise_for_status()
    logger.info(f"[iLoveAPI] Process complete")

    # Step 4: Download PDF to memory
    logger.info(f"[iLoveAPI] Downloading converted PDF...")
    download_res = requests.get(
        f"{server_url}/download/{task_id}", headers=headers, timeout=timeout
    )
    download_res.raise_for_status()
    logger.info(f"[iLoveAPI] PDF downloaded: {len(download_res.content) / 1024:.1f} KB")

    return download_res.content


# ==================== image-only PDF rendering ====================

def _render_pdf_to_image_pdf(pdf_bytes: bytes, scale: int = 3) -> bytes:
    """
    Render each page of a PDF as a high-res image and create an image-only PDF.
    All processing in memory, no disk I/O.

    Why? iLoveAPI/LibreOffice renders math formulas as vector paths in PDF.
    MinerU cannot extract these as text (produces '????'). By converting to
    images, MinerU is forced to use its VLM model which correctly OCRs
    formulas into LaTeX.
    """
    import fitz  # PyMuPDF

    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    img_doc = fitz.open()
    mat = fitz.Matrix(scale, scale)

    for page in src_doc:
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("jpeg", jpg_quality=95)
        rect = page.rect
        new_page = img_doc.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=img_bytes)

    result = img_doc.tobytes()
    page_count = len(src_doc)

    img_doc.close()
    src_doc.close()

    logger.info(f"[parse_pptx] Image-only PDF rendered: {len(result)/1024:.1f} KB, {page_count} pages")
    return result


# ==================== main parsing entrance ====================

def parse_pptx(pptx_path, filename, output_dir, base_llm_paras,
                     strategy="to_pdf_api", relative_root=None, baseurl=""):
    """
    PPTX parsing entrance, aligned with parse_pdfs / parse_docx pattern.

    strategy options:
        - "to_md":      directly extract from PPTX XML (pptx2md + MarkItDown)
        - "to_pdf":     use LibreOffice to convert to PDF, then parse via MinerU
        - "to_pdf_api": use iLoveAPI to convert to PDF, then parse via MinerU (recommended)
    """
    pptx_data = load_file_bytes(pptx_path, file_url=baseurl)
    logger.info(f"[parse_pptx] PPTX loaded: {len(pptx_data)/1024:.1f} KB")

    if strategy == "to_pdf_api":
        return _parse_pptx_via_api(pptx_data, filename, output_dir,
                                         base_llm_paras, relative_root)

    elif strategy == "to_pdf":
        return _parse_pptx_via_libreoffice(pptx_data, filename, output_dir,
                                                  base_llm_paras, relative_root)

    elif strategy == "to_md":
        return _parse_pptx_to_md(pptx_data, filename, output_dir,
                                       base_llm_paras, relative_root)

    else:
        raise ValueError(f"Unknown pptx strategy: {strategy}")


def _parse_pptx_via_api(pptx_data, filename, output_dir,
                               base_llm_paras, relative_root):
    """
    PPTX bytes → iLoveAPI PDF bytes → image-only PDF bytes → temp file → MinerU.
    Only ONE temp file write (for MinerU upload, which requires a file path).
    """
    # Step 1: PPTX → PDF (in memory)
    pdf_bytes = _pptx_bytes_to_pdf_bytes(pptx_data, filename)

    # Step 2: PDF → image-only PDF (in memory)
    img_pdf_bytes = _render_pdf_to_image_pdf(pdf_bytes)

    # Step 3: Write to output_dir for MinerU upload, then clean up
    tmp_path = os.path.join(output_dir, "_pptx_tmp.pdf")
    with open(tmp_path, "wb") as f:
        f.write(img_pdf_bytes)

    try:
        parsed_df = parse_pdfs(
            tmp_path, filename, output_dir, base_llm_paras,
            relative_root=relative_root
        )
        return parsed_df
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _parse_pptx_via_libreoffice(pptx_data, filename, output_dir,
                                       base_llm_paras, relative_root):
    """
    LibreOffice requires file paths (subprocess), so temp dir is unavoidable here.
    PPTX → temp file → LibreOffice → PDF → image-only PDF bytes → temp file → MinerU.
    """
    import shutil
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="pptx_lo_")
    try:
        # Write PPTX to temp (LibreOffice needs file path)
        local_pptx = os.path.join(tmp_dir, filename)
        local_pptx = path_handle(local_pptx, mode="sanitize")
        with open(local_pptx, "wb") as f:
            f.write(pptx_data)

        pdf_path, _ = pptx_to_pdf_libreoffice(local_pptx, tmp_dir)

        # Read PDF into memory, then same image-only PDF flow
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    img_pdf_bytes = _render_pdf_to_image_pdf(pdf_bytes)

    tmp_path = os.path.join(output_dir, "_pptx_tmp.pdf")
    with open(tmp_path, "wb") as f:
        f.write(img_pdf_bytes)

    try:
        parsed_df = parse_pdfs(
            tmp_path, filename, output_dir, base_llm_paras,
            relative_root=relative_root
        )
        return parsed_df
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _parse_pptx_to_md(pptx_data, filename, output_dir, base_llm_paras, relative_root):
    """Extract content from PPTX XML via pptx2md + MarkItDown → parse_md."""
    # pptx2md and MarkItDown require file paths
    local_pptx = os.path.join(output_dir, "_pptx_tmp.pptx")
    with open(local_pptx, "wb") as f:
        f.write(pptx_data)

    try:
        img_dir = os.path.join(output_dir, "images")
        os.makedirs(img_dir, exist_ok=True)
        temp_md_path = os.path.join(output_dir, "output.md")

        convert(
            ConversionConfig(
                pptx_path=local_pptx,
                output_path=temp_md_path,
                image_dir=img_dir
            )
        )

        md = MarkItDown(enable_plugins=False)
        result = md.convert(local_pptx)

        pattern = r'^!\[.*?\]\(.*?\.(?:png|jpe?g)\)$'
        md_imgs = find_images(output_dir)
        lines = result.text_content.splitlines()

        ppt_md_lines = []
        image_index = 0
        for line in lines:
            if image_index < len(md_imgs):
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    line = f"![image{image_index + 1}]({md_imgs[image_index]})"
                    image_index += 1
            ppt_md_lines.append(line)

        while image_index < len(md_imgs):
            ppt_md_lines.append(f"![image{image_index + 1}]({md_imgs[image_index]})")
            image_index += 1

        parsed_df = parse_md(
            output_dir, source_type="pptx",
            md_lines=ppt_md_lines, base_llm_paras=base_llm_paras,
            relative_root=relative_root
        )
        return parsed_df
    finally:
        if os.path.exists(local_pptx):
            os.remove(local_pptx)
