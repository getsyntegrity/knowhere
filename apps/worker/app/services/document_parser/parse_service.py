"""
main parsing service
"""
import os

from shared.core.config import settings
from shared.utils.file_utils import path_handle
from loguru import logger

# document_parser imports
from app.services.document_parser.doc_parser import convert_doc2dics, parse_docx
from app.services.document_parser.fragment_parser import parse_fragment
from app.services.document_parser.image_parser import parse_image
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.pdf_parser import parse_pdfs
from app.services.document_parser.table_parser import parse_xlsx
from app.services.document_parser.txt_parser import parse_texts


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
    
    # ========== 路径处理 ==========
    split_char = settings.SPLIT_CHAR or "/"
    kb_dir = kwargs.get('kb_dir', '默认目录')
    filename = path_handle(filename, mode="clean_single")
    
    # 构建相对根路径（用于 chunk 的 path 字段）
    kb_dir_parts = kb_dir.split(split_char)
    if filename and "images" not in kb_dir_parts:
        relative_root = "/".join(kb_dir_parts + [filename])
    else:
        relative_root = "/".join(kb_dir_parts)
    
    # 构建完整输出目录（output_dir + relative_root）
    full_output_dir = os.path.join(output_dir, relative_root.replace("/", os.sep))
    full_output_dir = path_handle(full_output_dir, mode="sanitize")
    os.makedirs(full_output_dir, exist_ok=True)
    
    logger.debug(f"relative_root: {relative_root}")
    logger.debug(f"full_output_dir: {full_output_dir}")
    # ========== 路径处理结束 ==========

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
        
    logger.debug(f"full_output_dir: {full_output_dir}")
    
    return full_output_dir, parsed_df

