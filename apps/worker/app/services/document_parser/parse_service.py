"""
main parsing service
"""
import os
import re

from shared.core.config import settings
from shared.utils.file_utils import path_handle
from loguru import logger
from shared.core.exceptions.domain_exceptions import (
    ValidationException,
    WorkerHandlingException,
)
from shared.core.exceptions.knowhere_exception import KnowhereException

# document_parser imports
from app.services.document_parser.doc_parser import convert_doc2dics, parse_docx
from app.services.document_parser.fragment_parser import parse_fragment
from app.services.document_parser.image_parser import parse_image
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.pdf_parser import parse_pdfs
from app.services.document_parser.table_parser import parse_xlsx
from app.services.document_parser.txt_parser import parse_texts


def cleanup_unreferenced_images(output_dir: str) -> int:
    """
    Clean up unreferenced UUID-named images from the images directory.
    
    After document parsing (PDF, DOCX, PPTX, etc.), the images/ directory may contain:
    1. Processed images: renamed with semantic names like 'image-0-xxx.jpg'
    2. Unreferenced images: UUID-named (64-char hex) that were parsed as tables/formulas
    
    This function removes the unreferenced UUID-named images to reduce final package size.
    
    Args:
        output_dir: The full output directory path
    
    Returns:
        Number of files removed
    """
    img_dir = os.path.join(output_dir, "images")
    if not os.path.isdir(img_dir):
        return 0
    
    # UUID pattern: 64 hex characters followed by image extension
    uuid_pattern = re.compile(r'^[a-f0-9]{64}\.(?:jpg|jpeg|png|gif|webp)$', re.IGNORECASE)
    
    removed_count = 0
    for filename in os.listdir(img_dir):
        if uuid_pattern.match(filename):
            file_path = os.path.join(img_dir, filename)
            try:
                os.remove(file_path)
                removed_count += 1
                logger.debug(f"Removed unreferenced image: {filename}")
            except OSError as e:
                logger.warning(f"Failed to remove {filename}: {e}")
    
    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} unreferenced UUID-named images from {img_dir}")
    
    return removed_count


async def checkerboard_inject_parse(
    file_full_path: str, 
    filename: str, 
    output_dir: str,
    **kwargs
):
    """
    main parsing function
    
    Args:
        file_full_path: source file path (local or URL)
        filename: file name
        output_dir: output directory (absolute path, caller provides)
        **kwargs: parsing parameters
            - kb_dir: sub-directory name (default: "默认目录")
            - smart_title_parse, summary_image, summary_table, summary_txt
            - stopwords, doc_type, add_frag_desc, base_url
    
    Returns:
        tuple: (output_dir, parsed_df)
            - output_dir: directory path after parsing
            - parsed_df: parsed content DataFrame
    """
    # 构建 base_llm_paras（从 kwargs 获取）
    base_llm_paras = {
        "llm_histories": kwargs.get('llm_histories', 5),
        "smart_title_parse": kwargs.get('smart_title_parse', True),
        "summary_image": kwargs.get('summary_image', True),
        "summary_table": kwargs.get('summary_table', True),
        "summary_txt": kwargs.get('summary_txt', True),
        "stopwords": kwargs.get('stopwords', []),
        "doc_type": kwargs.get('doc_type', 'auto'),
        "frag_desc": kwargs.get('add_frag_desc', ''),
    }
    
    baseurl = kwargs.get('base_url', '')
        
    logger.debug(f"baseurl: {baseurl}")
    logger.debug(f"file_full_path: {file_full_path}")
    
    # ========== Path handling ==========
    split_char = settings.SPLIT_CHAR or "/"
    kb_dir = kwargs.get('kb_dir', 'Default_Root')
    filename = path_handle(filename, mode="clean_single")
    
    # Develop relative root path for chunk path field
    kb_dir_parts = kb_dir.split(split_char)
    if filename and "images" not in kb_dir_parts:
        relative_root = "/".join(kb_dir_parts + [filename])
    else:
        relative_root = "/".join(kb_dir_parts)
    
    # Develop full output directory (output_dir + relative_root)
    full_output_dir = os.path.join(output_dir, relative_root.replace("/", os.sep))
    full_output_dir = path_handle(full_output_dir, mode="sanitize")
    os.makedirs(full_output_dir, exist_ok=True)
    
    logger.debug(f"relative_root: {relative_root}")
    logger.debug(f"full_output_dir: {full_output_dir}")

    file_path_lower = file_full_path.lower()
    parsed_df = None
    
    if ".fragment" in file_path_lower:
        logger.debug("file type is fragment")
        fragment_content = kwargs.get('fragment_content', '')
        full_output_dir, relative_root, parsed_df = await parse_fragment(fragment_content, filename=filename, output_dir=output_dir, kb_dir=kb_dir, base_llm_paras=base_llm_paras)

    elif '.txt' in file_path_lower:
        logger.debug("file type is txt")
        txt_lines = await parse_texts(file_path=file_full_path, baseurl=baseurl)
        parsed_df = await parse_md(full_output_dir, source_type='md', md_lines=txt_lines, base_llm_paras=base_llm_paras, relative_root=relative_root)

    elif ('.png' in file_path_lower or '.jpg' in file_path_lower or '.jpeg' in file_path_lower):
        logger.debug(f"file type is image")
        parsed_df = await parse_image(file_full_path, filename=filename, output_dir=full_output_dir, baseurl=baseurl, base_llm_paras=base_llm_paras, relative_root=relative_root)

    elif '.pdf' in file_path_lower:
        logger.debug(f"file type is pdf")
        if filename and file_full_path:
            parsed_df = await parse_pdfs(file_full_path, filename=filename, output_dir=full_output_dir, base_llm_paras=base_llm_paras, mode="api", relative_root=relative_root)

    elif '.docx' in file_path_lower:
        logger.debug(f"file type is docx")
        if filename and file_full_path:
            parsed_structure, df_list = await parse_docx(file_full_path, base_llm_paras, full_output_dir, filename, baseurl, relative_root=relative_root)
            parsed_df = await convert_doc2dics(parsed_structure, df_list, full_output_dir, base_llm_paras=base_llm_paras, relative_root=relative_root)

    elif '.xlsx' in file_path_lower:
        logger.debug(f"file type is xlsx")
        if filename and file_full_path:
            parsed_df = await parse_xlsx(file_full_path, filename, full_output_dir, baseurl, base_llm_paras=base_llm_paras, relative_root=relative_root)

    elif '.pptx' in file_path_lower:
        logger.debug(f"file type is pptx")
        if filename and file_full_path:
            parsed_df = await parse_pdfs(file_full_path, filename=filename, output_dir=full_output_dir, base_llm_paras=base_llm_paras, mode="api", relative_root=relative_root)

    elif '.md' in file_path_lower:
        logger.debug(f"file type is md")
        if filename and file_full_path:
            parsed_df = await parse_md(full_output_dir, source_type="md", file_path=file_full_path, base_llm_paras=base_llm_paras, relative_root=relative_root)

    elif '.json' in file_path_lower:
        logger.debug(f"file type is json")
        # JSON parsing not yet implemented
        
    else:
        # Unsupported file type
        file_ext = os.path.splitext(file_full_path)[1].lower()
        supported_types = ['.txt', '.fragment', '.png', '.jpg', '.jpeg', '.pdf', '.docx', '.xlsx', '.pptx', '.md', '.json']
        raise ValidationException(
            user_message=f"Unsupported file type: {file_ext}",
            violations=[{
                "field": "file_type",
                "description": f"Must be one of: {', '.join(supported_types)}"
            }]
        )
        
    logger.debug(f"full_output_dir: {full_output_dir}")
    
    # Post-processing: clean up unreferenced UUID-named images
    cleanup_unreferenced_images(full_output_dir)
    
    return full_output_dir, parsed_df

