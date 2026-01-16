"""
解析服务入口
从 knowledge_base_service.py 迁移，仅保留文件解析功能
"""
import os

from shared.core.config import settings
from shared.core.context import get_current_user
from shared.models.database.user import User
from shared.services.redis import RedisServiceFactory
from shared.utils.CommonHelper import is_remote
from shared.utils.file_utils import path_handle
from loguru import logger

# document_parser imports
from app.services.document_parser.doc_parser import convert_doc2dics, parse_docx
from app.services.document_parser.image_parser import parse_image
from app.services.document_parser.md_parser import parse_md
from app.services.document_parser.pdf_parser import parse_pdfs
from app.services.document_parser.table_parser import parse_xlsx
from app.services.document_parser.txt_parser import parse_texts


async def checkerboard_inject_parse(
    file_full_path, 
    filename, 
    user_config: dict = None,
    **kwargs
):
    """
    解析文档
    
    Args:
        file_full_path: 文件完整路径
        filename: 文件名
        user_config: 用户配置字典（可选，如果不提供则从上下文获取）
        **kwargs: 其他参数
    
    Returns:
        tuple: (kb_dir, parsed_df)
            - kb_dir: directory path after parsing
            - parsed_df: parsed content DataFrame (pandas.DataFrame)
    """
    # 如果没有传入user_config，则从上下文获取（兼容旧调用方式）
    if user_config is None:
        user_context: User | None = get_current_user()
        redis_service = RedisServiceFactory.get_service()
        from shared.services.redis.user_redis_service import UserRedisService
        user_redis_service = UserRedisService(redis_service)
        
        if not user_context:
            raise ValueError("User context is empty")
        
        user_config = await user_redis_service.get_user_config(str(user_context.id))
        if not user_config:
            from app.services.user.user_config_service import UserConfigService
            import json
            user_dic_str = UserConfigService.init_user(str(user_context.id))
            user = json.loads(user_dic_str) if isinstance(user_dic_str, str) else user_dic_str
            await user_redis_service.save_user_config(str(user_context.id), user)
        else:
            user = user_config
    else:
        # 使用传入的user_config
        user = user_config
    
    # 构建base_llm_paras
    base_llm_paras = {
        "llm_histories": user['USER_SETTINGS']['llm_histories'],
        "smart_title_parse": kwargs.get('smart_title_parse', True),
        "summary_image": kwargs.get('summary_image', True),
        "summary_table": kwargs.get('summary_table', True),
        "summary_txt": kwargs.get('summary_txt', True),
        "stopwords": user.get('stopwords', []),
        "doc_type": kwargs.get('doc_type', 'auto'),
        "frag_desc": kwargs.get('add_frag_desc', ''),
    }
    
    try:
        baseurl = kwargs.get('base_url', '')
    except:
        baseurl = ""
        
    logger.debug(f"baseurl: {baseurl}")
    logger.debug(f"file_full_path: {file_full_path}")

    if is_remote(file_full_path):
        # 如果已经是完整的URL（预签名URL），直接使用
        # 不需要调用 get_pub_fileurl()
        pass  # TODO: 后续需要处理
    # 对于本地文件，保持原始路径，不要替换为.fragment
    # file_full_path 保持原值

    split_char = settings.SPLIT_CHAR or ";"
    kb_dir = kwargs.get('kb_dir', '默认目录')
    dir_terms = kb_dir.split(split_char)
    dir_terms.insert(0, user['KB_PATH'])
    filename = path_handle(filename, mode="clean_single")
    
    if not "images" in dir_terms and filename is not None:
        dir_terms.append(filename)

    kb_dir = path_handle(os.path.join(*dir_terms), mode="sanitize")
    os.makedirs(kb_dir, exist_ok=True)

    file_path_lower = file_full_path.lower()

    parsed_df = None
    
    if '.txt' in file_path_lower or ".fragment" in file_path_lower:
        logger.debug(f"file type is txt or fragment")
        try:
            fragment_content = kwargs.get('fragment_content')
        except:
            fragment_content = None
        txt_lines = await parse_texts(file_path=file_full_path, fragment_content=fragment_content, baseurl=baseurl)
        parsed_df = await parse_md(kb_dir, source_type='md', md_lines=txt_lines, base_llm_paras=base_llm_paras)

    elif ('.png' in file_path_lower or '.jpg' in file_path_lower or '.jpeg' in file_path_lower) or ".fragment" in file_path_lower:
        logger.debug(f"file type is image")
        parsed_df = await parse_image(file_full_path, filename=filename, kb_dir=kb_dir, baseurl=baseurl, base_llm_paras=base_llm_paras)

    elif '.pdf' in file_path_lower:
        logger.debug(f"file type is pdf")
        if filename is not None and file_full_path is not None:
            parsed_df = await parse_pdfs(file_full_path, filename=filename, output_dir=kb_dir, base_llm_paras=base_llm_paras, mode="api")

    elif '.docx' in file_path_lower:
        logger.debug(f"file type is docx")
        if filename is not None and file_full_path is not None:
            parsed_structure, df_list = await parse_docx(file_full_path, base_llm_paras, kb_dir, filename, baseurl)
            parsed_df = await convert_doc2dics(parsed_structure, df_list, kb_dir, base_llm_paras=base_llm_paras)

    elif '.xlsx' in file_path_lower:
        logger.debug(f"file type is xlsx")
        if filename is not None and file_full_path is not None:
            parsed_df = await parse_xlsx(file_full_path, filename, kb_dir, baseurl, base_llm_paras=base_llm_paras)

    elif '.pptx' in file_path_lower:
        logger.debug(f"file type is pptx")
        if filename is not None and file_full_path is not None:
            parsed_df = await parse_pdfs(file_full_path, filename=filename, output_dir=kb_dir, base_llm_paras=base_llm_paras, mode="api")

    elif '.md' in file_path_lower:
        logger.debug(f"file type is md")
        if filename is not None and file_full_path is not None:
            parsed_df = await parse_md(kb_dir, source_type="md", file_path=file_full_path, base_llm_paras=base_llm_paras)

    elif '.json' in file_path_lower:
        logger.debug(f"file type is json")
        
    logger.debug(f"kb_dir: {kb_dir}")
    
    return kb_dir, parsed_df
