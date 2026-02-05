"""
知识库相关控制器 - 仅保留必要的API
"""

from app.core.dependencies import get_current_user_id
from shared.models.schemas.files import (FileDirectoryCreateDto, FileDirectoryDto,
                                      FileDirectoryListDto,
                                      FileDirectoryUpdateDto)
from app.repositories.knowledge_base_repository import (create_directory,
                                                        delete_directory,
                                                        update_directory)
from fastapi import APIRouter, Depends
from starlette import status
from shared.core.exceptions.domain_exceptions import KnowledgeBaseOperationException

router = APIRouter(tags=["知识库"])

# 文件上传API已移除，请使用统一的 /v1/jobs 接口

# 目录管理API
@router.post('/create_directory', status_code=status.HTTP_201_CREATED, summary="增加SQL路径",description="用户注入知识路径")
async def add_sql_path(request_data: FileDirectoryCreateDto, user_id: str = Depends(get_current_user_id)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        request_data.user_id = user_id
        from shared.core.database import get_db_context
        async with get_db_context() as db:
            if await create_directory(db, request_data):
                return {"message": "创建目录成功"}
        raise KnowledgeBaseOperationException(
            internal_message="Failed to create directory"
        )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"创建目录失败:{e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to create directory: {str(e)}"
        )

@router.post('/delete_directory', status_code=status.HTTP_201_CREATED, summary="删除SQL路径",description="用户删除知识路径")
async def delete_sql_path(request_data: FileDirectoryDto, user_id: str = Depends(get_current_user_id)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        request_data.user_id = user_id
        from shared.core.database import get_db_context
        async with get_db_context() as db:
            if await delete_directory(db, request_data.id):
                return {"message": "删除目录成功"}
        raise KnowledgeBaseOperationException(
            internal_message="Failed to delete directory"
        )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"删除目录失败:{e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to delete directory: {str(e)}"
        )

@router.post('/update_directory', status_code=status.HTTP_201_CREATED, summary="更新SQL路径",description="用户更新知识路径")
async def update_sql_path(request_data: FileDirectoryUpdateDto, user_id: str = Depends(get_current_user_id)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        request_data.user_id = user_id
        from shared.core.database import get_db_context
        async with get_db_context() as db:
            if await update_directory(db, request_data):
                return {"message": "更新目录成功"}
        raise KnowledgeBaseOperationException(
            internal_message="Failed to update directory"
        )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"更新目录失败:{e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to update directory: {str(e)}"
        )

@router.post('/get_directory', status_code=status.HTTP_201_CREATED, summary="获取用户知识库路径",description="用户获取知识路径")
async def get_sql_path(user_id: str = Depends(get_current_user_id)):
    """
    获取用户知识库目录树，如果用户没有目录则自动创建默认目录
    """
    try:
        from shared.core.database import get_db_context
        from shared.models.schemas.files import FileDirectoryCreateDto
        from app.repositories.knowledge_base_repository import (
            create_directory, get_directories, get_directories_by_user)
        
        async with get_db_context() as db:
            # 获取用户的所有目录
            user_directories = await get_directories_by_user(db, user_id)
            
            # 如果用户没有目录，创建默认目录
            if not user_directories:
                create_request = FileDirectoryCreateDto(
                    title="默认目录",
                    parent_id=None,
                    user_id=user_id
                )
                
                success = await create_directory(db, create_request)
                if not success:
                    from loguru import logger
                    logger.error(f"创建默认目录失败: user_id={user_id}")
                    raise KnowledgeBaseOperationException(
                        internal_message="Failed to create default directory"
                    )
            
            # 获取目录树结构
            directories = await get_directories(db, user_id)
            return directories
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"获取目录失败:{e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to get directory: {str(e)}"
        )

@router.post('/list_directory', status_code=status.HTTP_201_CREATED, summary="知识详情",description="根据用户路径获取知识点")
async def list_directory(request_data: FileDirectoryListDto, user_id: str = Depends(get_current_user_id)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        from shared.core.database import get_db_context
        from app.repositories.knowledge_base_repository import \
            get_directory_contents
        async with get_db_context() as db:
            contents = await get_directory_contents(db, request_data.id)
            return contents
    except Exception as e:
        from loguru import logger
        logger.error(f"获取目录内容失败:{e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to get directory contents: {str(e)}"
        )

# 添加知识库路径API
@router.post('/add_kb', status_code=status.HTTP_201_CREATED, summary="添加知识库路径", description="添加知识库路径")
async def add_kb_path(request_data: dict, user_id: str = Depends(get_current_user_id)):
    """
    添加知识库路径
    """
    try:
        from shared.core.database import get_db_context
        from shared.models.schemas.files import FileDirectoryCreateDto
        from app.repositories.knowledge_base_repository import create_directory

        # 构建目录创建请求
        create_request = FileDirectoryCreateDto(
            title=request_data.get('path', ''),
            parent_id=None,  # 默认为根目录
            user_id=user_id
        )
        
        async with get_db_context() as db:
            success = await create_directory(db, create_request)
            if success:
                return {"message": "知识库路径添加成功"}
            else:
                raise KnowledgeBaseOperationException(
                    internal_message="Failed to add knowledge base path"
                )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"添加知识库路径失败: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to add knowledge base path: {str(e)}"
        )

# 临时文件上传API已移除，请使用统一的 /v1/jobs 接口

# 注意：以下旧方案同步API已删除，请使用新的异步API: /v1/jobs
# - /add_kb_data (增加知识内容)
# - /add_kb_fragment (增加知识碎片)  
# - /search (知识库搜索) - 已移除，请使用Worker服务处理
# - /get_kb_data (查询知识库信息)
# - /delete_kb_data (删除知识信息)
# - /delete_kb (删除知识库)
# - /encode_know (向量化知识文件)
# - /get_fragments (查看知识片段)
# - /get_fileTree (查看知识树)
# - /tree_kb (建立单树结构)
# - /forest_kb (建立森林结构)

# 添加知识库内容删除API
@router.delete('/contents/{content_id}', status_code=status.HTTP_200_OK, summary="删除知识库内容或目录", description="根据ID自动判断删除内容或目录")
async def delete_knowledge_content(
    content_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    删除知识库内容或目录
    根据ID类型自动判断是删除内容还是目录
    """
    try:
        from shared.core.database import get_db_context
        from app.repositories.knowledge_base_repository import (
            delete_directory, delete_kb_content)
        from sqlalchemy import text
        
        async with get_db_context() as db:
            # 首先检查是否是目录
            result = await db.execute(text('SELECT id FROM file_directory WHERE id = :id'), {'id': content_id})
            is_directory = result.fetchone() is not None
            
            if is_directory:
                # 删除目录
                success = await delete_directory(db, content_id)
                if success:
                    return {"message": "目录删除成功"}
                else:
                    raise KnowledgeBaseOperationException(
                        internal_message="Failed to delete directory"
                    )
            else:
                # 删除内容
                success = await delete_kb_content(db, content_id)
                if success:
                    return {"message": "内容删除成功"}
                else:
                    raise KnowledgeBaseOperationException(
                        internal_message="Failed to delete content"
                    )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger
        logger.error(f"删除知识库内容失败: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to delete knowledge base content: {str(e)}"
        )