import os
import re
import subprocess

from app.core.config import settings
from app.services.common.kb_utils import find_images
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.pdf_parser import parse_pdfs
from app.utils.CommonHelper import load_file_bytes
from app.utils.file_utils import path_handle
from app.utils.FileDownUpUtils import s3_upload_file
from fastapi import UploadFile
from markitdown import MarkItDown
from pptx import Presentation
from pptx2md import ConversionConfig, convert


def pptx2md_lines(pptx_path, kb_dir):
    prs = Presentation(pptx_path)

    md_lines = []

    for i, slide in enumerate(prs.slides, start=1):
        md_lines.append(f"# 第{i}页")

        # --- 文本 ---
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                txt = shape.text.strip()
                if txt:
                    texts.append(txt)
        if texts:
            md_lines.append("## 文本")
            for t in texts:
                md_lines.append(f"- {t}")

        # --- 图片 ---
        imgs = []
        for shape in slide.shapes:
            if shape.shape_type == 13:  # PICTURE
                imgs.append("图片对象 (已提取)")
        if imgs:
            md_lines.append("## 图片")
            for idx, _ in enumerate(imgs, start=1):
                md_lines.append(f"- 第{i}页的图片 {idx}")

        # --- 表格 ---
        tables = []
        for shape in slide.shapes:
            if shape.has_table:
                table = shape.table
                rows = []
                for r in table.rows:
                    row_texts = [c.text.strip() for c in r.cells]
                    rows.append(" | ".join(row_texts))
                tables.append(rows)
        if tables:
            md_lines.append("## 表格")
            for tid, rows in enumerate(tables, start=1):
                md_lines.append(f"- 表格{tid}:")
                for row in rows:
                    md_lines.append(f"  - {row}")

        # --- 注释 ---
        if slide.has_notes_slide:
            notes_slide = slide.notes_slide
            notes = []
            for shape in notes_slide.shapes:
                if shape.has_text_frame:
                    n = shape.text.strip()
                    if n:
                        notes.append(n)
            if notes:
                md_lines.append("## 注释")
                for note in notes:
                    md_lines.append(f"- {note}")

        md_lines.append("")  # 页尾空行


    return ""

def pptx_to_pdf(pptx_path, outdir="."):
    soffice_path = settings.LIBER_OFFICE or "/usr/bin/libreoffice"
    from app.core.constants import ProcessingConstants
    filter_opts = f"Quality={ProcessingConstants.IMG_QUALITY};ReduceImageResolution=false;UseTaggedPDF=true,ExportNotes=true"
    subprocess.run([
        soffice_path, "--headless",
        "--convert-to", f"pdf:writer_pdf_Export:{filter_opts}",
        pptx_path, "--outdir", outdir
    ], check=True)

    base = os.path.splitext(os.path.basename(pptx_path))[0]
    pdf_path = os.path.join(outdir, base + ".pdf")
    return pdf_path, (base + ".pdf")

async def parse_pptx2md(raw_file_path, filename, baseurl, kb_dir, temp_md_path, temp_source_dir, base_llm_paras, strategy="to_pdf"):
    pptx_data = await load_file_bytes(raw_file_path, file_url=baseurl)
    pptx_source_path = os.path.join(temp_source_dir, filename)
    pptx_source_path = path_handle(pptx_source_path, mode="sanitize")
    with open(pptx_source_path, "wb") as f:
        f.write(pptx_data)

    # 不管采用何种策略 核心都是把ppt变成md_lines
    if strategy == "to_md":
        # 使用pptx2md包提取图片内容
        convert(
            ConversionConfig(
                pptx_path=pptx_source_path,
                output_path=temp_md_path,
                image_dir=os.path.join(kb_dir, "images")
            )
        )

        # 使用 MS markitdown 提取文本内容
        md = MarkItDown(enable_plugins=False)
        result = md.convert(raw_file_path)

        # 对齐图片和文本内容
        pattern = r'^!\[.*?\]\(.*?\.(?:png|jpe?g)\)$'
        md_imgs = find_images(kb_dir)
        lines = result.text_content.splitlines()

        ppt_md_lines = []
        image_index = 0
        for line in lines:
            if image_index < len(md_imgs):

                if re.match(pattern, line.strip(), re.IGNORECASE):
                    line = f"![图像{image_index + 1}]({md_imgs[image_index]})"
                    image_index += 1
            ppt_md_lines.append(line)

        # 如果有剩余图像未插入（说明文本中没有足够占位符），追加到末尾
        while image_index < len(md_imgs):
            ppt_md_lines.append(f"![图像{image_index + 1}]({md_imgs[image_index]})")
            image_index += 1

        doc_graph = await parse_md(kb_dir, source_type="pptx", md_lines=ppt_md_lines, base_llm_paras=base_llm_paras)
        return doc_graph

    elif strategy == "to_pdf":
        # base_llm_paras.update({"summary_image": False})
        base_llm_paras.update({"summary_table": False})
        # base_llm_paras.update({"summary_txt": False})

        pptx_pdf_path, pdf_name = pptx_to_pdf(pptx_source_path, temp_source_dir)
        f = open(pptx_pdf_path, "rb")
        pptx_pdf = UploadFile(filename=os.path.basename(pptx_pdf_path), file=f)
        prefix = os.sep.join(temp_source_dir.split(os.sep)[1:])
        content = s3_upload_file(pptx_pdf, prefix=prefix)

        doc_graph = await parse_pdfs(content['public_url_for_reference'], filename, kb_dir, base_llm_paras, mode="api")
        return doc_graph

    else:
        return {}