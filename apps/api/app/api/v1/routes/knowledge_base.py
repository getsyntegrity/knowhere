"""
知识库相关控制器 - 仅保留必要的API
"""
import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from starlette import status
from app.core.dependencies import get_redis_service
from app.services.redis import RedisService
from app.core.dependencies import get_current_user
from app.repositories.knowledge_base_repository import create_directory, delete_directory, update_directory
from app.models.schemas.files import FileDirectoryDto, FileDirectoryCreateDto, FileDirectoryUpdateDto, FileDirectoryListDto
from app.models.database.user import User
from app.utils.FileDownUpUtils import s3_upload_file

router = APIRouter(tags=["知识库"])

# 文件上传API已移除，请使用统一的 /v1/jobs 接口

# 目录管理API
@router.post('/create_directory', status_code=status.HTTP_201_CREATED, summary="增加SQL路径",description="用户注入知识路径")
async def add_sql_path(request_data: FileDirectoryCreateDto, current_user: User = Depends(get_current_user)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        request_data.user_id = current_user.id
        from app.core.database import get_db_context
        async with get_db_context() as db:
            if await create_directory(db, request_data):
                return {"message": "创建目录成功"}
        raise HTTPException(status_code=400, detail="创建目录失败")
    except Exception as e:
        from loguru import logger
        logger.error(f"创建目录失败:{e}")
        raise HTTPException(status_code=400, detail="创建目录失败")

@router.post('/delete_directory', status_code=status.HTTP_201_CREATED, summary="删除SQL路径",description="用户删除知识路径")
async def delete_sql_path(request_data: FileDirectoryDto, current_user: User = Depends(get_current_user)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        request_data.user_id = current_user.id
        from app.core.database import get_db_context
        async with get_db_context() as db:
            if await delete_directory(db, request_data.id):
                return {"message": "删除目录成功"}
        raise HTTPException(status_code=400, detail="删除目录失败")
    except Exception as e:
        from loguru import logger
        logger.error(f"删除目录失败:{e}")
        raise HTTPException(status_code=400, detail="删除目录失败")

@router.post('/update_directory', status_code=status.HTTP_201_CREATED, summary="更新SQL路径",description="用户更新知识路径")
async def update_sql_path(request_data: FileDirectoryUpdateDto, current_user: User = Depends(get_current_user)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        request_data.user_id = current_user.id
        from app.core.database import get_db_context
        async with get_db_context() as db:
            if await update_directory(db, request_data):
                return {"message": "更新目录成功"}
        raise HTTPException(status_code=400, detail="更新目录失败")
    except Exception as e:
        from loguru import logger
        logger.error(f"更新目录失败:{e}")
        raise HTTPException(status_code=400, detail="更新目录失败")

@router.post('/get_directory', status_code=status.HTTP_201_CREATED, summary="获取用户知识库路径",description="用户获取知识路径")
async def get_sql_path(current_user: User = Depends(get_current_user)):
    """
    获取用户知识库目录树，如果用户没有目录则自动创建默认目录
    """
    try:
        from app.core.database import get_db_context
        from app.repositories.knowledge_base_repository import get_directories, get_directories_by_user, create_directory
        from app.models.schemas.files import FileDirectoryCreateDto
        
        async with get_db_context() as db:
            # 获取用户的所有目录
            user_directories = await get_directories_by_user(db, str(current_user.id))
            
            # 如果用户没有目录，创建默认目录
            if not user_directories:
                create_request = FileDirectoryCreateDto(
                    title="默认目录",
                    parent_id=None,
                    user_id=str(current_user.id)
                )
                
                success = await create_directory(db, create_request)
                if not success:
                    from loguru import logger
                    logger.error(f"创建默认目录失败: user_id={current_user.id}")
                    raise HTTPException(status_code=400, detail="创建默认目录失败")
            
            # 获取目录树结构
            directories = await get_directories(db, current_user.id)
            return directories
    except Exception as e:
        from loguru import logger
        logger.error(f"获取目录失败:{e}")
        raise HTTPException(status_code=400, detail="获取目录失败")

@router.post('/list_directory', status_code=status.HTTP_201_CREATED, summary="知识详情",description="根据用户路径获取知识点")
async def list_directory(request_data: FileDirectoryListDto, current_user: User = Depends(get_current_user)):
    """
    模拟知识库知识片段增加的时候，增加目录树
    """
    try:
        from app.core.database import get_db_context
        from app.repositories.knowledge_base_repository import get_directory_contents
        async with get_db_context() as db:
            contents = await get_directory_contents(db, request_data.id)
            return contents
    except Exception as e:
        from loguru import logger
        logger.error(f"获取目录内容失败:{e}")
        raise HTTPException(status_code=400, detail="获取目录内容失败")

# 添加知识库路径API
@router.post('/add_kb', status_code=status.HTTP_201_CREATED, summary="添加知识库路径", description="添加知识库路径")
async def add_kb_path(request_data: dict, current_user: User = Depends(get_current_user)):
    """
    添加知识库路径
    """
    try:
        from app.core.database import get_db_context
        from app.repositories.knowledge_base_repository import create_directory
        from app.models.schemas.files import FileDirectoryCreateDto
        
        # 构建目录创建请求
        create_request = FileDirectoryCreateDto(
            title=request_data.get('path', ''),
            parent_id=None,  # 默认为根目录
            user_id=current_user.id
        )
        
        async with get_db_context() as db:
            success = await create_directory(db, create_request)
            if success:
                return {"message": "知识库路径添加成功"}
            else:
                raise HTTPException(status_code=400, detail="知识库路径添加失败")
    except Exception as e:
        from loguru import logger
        logger.error(f"添加知识库路径失败: {e}")
        raise HTTPException(status_code=400, detail="添加知识库路径失败")

# 临时文件上传API已移除，请使用统一的 /v1/jobs 接口

# 注意：以下旧方案同步API已删除，请使用新的异步API: /v1/kb/jobs
# - /add_kb_data (增加知识内容)
# - /add_kb_fragment (增加知识碎片)  
# - /search (知识库搜索) - 已恢复
# - /get_kb_data (查询知识库信息)
# - /delete_kb_data (删除知识信息)
# - /delete_kb (删除知识库)
# - /encode_know (向量化知识文件)
# - /get_fragments (查看知识片段)
# - /get_fileTree (查看知识树)
# - /tree_kb (建立单树结构)
# - /forest_kb (建立森林结构)

# 恢复知识库搜索API
@router.post('/search', status_code=status.HTTP_200_OK, summary="知识库搜索", description="搜索知识库内容并获取AI回答")
async def search_knowledge_base(
    request_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    搜索知识库内容
    """
    try:
        from app.core.database import get_db_context
        from app.services.knowledge.knowledge_base_service import checkerboard_find
        # Redis服务已在共享包中
        from app.services.redis.user_redis_service import UserRedisService
        from app.services.user.user_config_service import UserConfigService
        import json
        
        # 获取用户配置
        redis_service = await get_redis_service()
        user_redis_service = UserRedisService(redis_service)
        user_config = await user_redis_service.get_user_config(str(current_user.id))
        
        if not user_config:
            # 初始化用户配置
            user_dic_str = UserConfigService.init_user(str(current_user.id))
            user_config = json.loads(user_dic_str) if isinstance(user_dic_str, str) else user_dic_str
            await user_redis_service.save_user_config(str(current_user.id), user_config)
        
        # 构建用户信息对象
        user_info = {
            'USER_SETTINGS': user_config,
            'stopwords': user_config.get('STOPWORDS', [])
        }
        
        # 调用搜索服务
        result = await checkerboard_find(
            user=user_info,
            user_message=request_data.get('question', ''),
            topk=request_data.get('topk', 3),
            rerank=request_data.get('rerank', True),
            signal_paths=request_data.get('filter_nodes', []),
            data_type=request_data.get('filter_type', 1),
            filter_mode=request_data.get('filter_mode', 'include')
        )
        
        return result
        
    except Exception as e:
        from loguru import logger
        logger.error(f"知识库搜索失败: {e}")
        raise HTTPException(status_code=400, detail="搜索失败")

# 添加知识库内容删除API
@router.delete('/contents/{content_id}', status_code=status.HTTP_200_OK, summary="删除知识库内容或目录", description="根据ID自动判断删除内容或目录")
async def delete_knowledge_content(
    content_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除知识库内容或目录
    根据ID类型自动判断是删除内容还是目录
    """
    try:
        from app.core.database import get_db_context
        from app.repositories.knowledge_base_repository import delete_kb_content, delete_directory
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
                    raise HTTPException(status_code=400, detail="目录删除失败")
            else:
                # 删除内容
                success = await delete_kb_content(db, content_id)
                if success:
                    return {"message": "内容删除成功"}
                else:
                    raise HTTPException(status_code=400, detail="内容删除失败")
    except Exception as e:
        from loguru import logger
        logger.error(f"删除知识库内容失败: {e}")
        raise HTTPException(status_code=400, detail="删除失败")