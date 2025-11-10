from typing import List, Optional

from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context
from app.models.database import knowledge_base as KBModels
from app.models.database.knowledge_base import KBPydantic, PathPydantic, PathBase, ContentBase, FileDirectory
from app.models.schemas.files import FileDirectoryUpdateDto, FileDirectoryDto, FileDirectoryCreateDto


async def create_update_kb(kbs:list[KBPydantic]) -> bool:
    """
    创建或更新知识库
    :param kbs:
    :return:
    """
    if not kbs:
        return True
    #对象转换
    object_mappings = []
    for kb in kbs:
        data_dict = kb.model_dump()
        processed_dict = {
            key: (value if value is not None else '')
            for key, value in data_dict.items()
        }
        object_mappings.append(processed_dict)
    async with get_db_context() as db:
        try:
            #bulk_insert_mappings处理ORM数据集
            await db.run_sync(
                lambda session: session.bulk_insert_mappings(ContentBase, object_mappings)
            )
            await db.commit()
            logger.info(f"批量插入{len(object_mappings)}条记录成功")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"批量插入记录时发生错误: {e}")
            return False

async def create_update_path(paths:list[PathPydantic]) -> bool:
    """
    创建或更新知识库路径
    :param paths:
    :return:
    """
    if not paths:
        return True
    path_mappings = []
    for path in paths:
        data_dict = path.model_dump()

        processed_dict = {
            key: (value if value is not None else '')
            for key, value in data_dict.items()
        }
        path_mappings.append(processed_dict)
    async with get_db_context() as db:
        try:
            await db.run_sync(
                lambda session: session.bulk_insert_mappings(PathBase, path_mappings)
            )
            await db.commit()
            logger.info(f"批量插入{len(path_mappings)}条记录成功")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"批量插入记录时发生错误: {e}")
            return False

async def get_kb_by_id(kb_id:str) -> KBPydantic|None:
    """
    根据id获取知识库
    :param kb_id:
    :return:
    """

async def get_directories(db: AsyncSession, user_id: str) -> List[dict]:
    """
    获取用户的目录树结构
    :param db: 数据库会话
    :param user_id: 用户ID
    :return: 目录树结构列表
    """
    return await build_directory_tree(db, user_id)

async def get_directory_contents(db: AsyncSession, directory_id: str) -> List[dict]:
    """
    根据目录ID获取该目录下的知识库内容
    :param db: 数据库会话
    :param directory_id: 目录ID
    :return: 知识库内容列表
    """
    try:
        # 首先获取目录信息
        directory = await get_directory_by_id(db, directory_id)
        if not directory:
            return []
        
        # 根据目录title在ContentBase的path字段中查找相关内容
        # 使用 ; 分隔符进行前缀匹配，格式：{kb_dir};{document_name};{section}
        split_char = ";"
        directory_prefix = directory.title + split_char
        result = await db.execute(
            select(ContentBase)
            .filter(ContentBase.path.startswith(directory_prefix))
            .order_by(ContentBase.id)
        )
        contents = result.scalars().all()
        
        # 转换为字典格式
        content_list = []
        for content in contents:
            content_dict = {
                "id": content.id,
                "content": content.content,
                "path": content.path,
                "type": content.type,
                "length": content.length,
                "keywords": content.keywords,
                "summary": content.summary,
                "know_id": content.know_id,
                "tokens": content.tokens,
                "embedding": content.embedding
            }
            content_list.append(content_dict)
        
        return content_list
    except Exception as e:
        logger.error(f"获取目录内容失败: {e}")
        return []

async def delete_kb_content(db: AsyncSession, content_id: str) -> bool:
    """
    根据内容ID删除知识库内容
    :param db: 数据库会话
    :param content_id: 内容ID
    :return: 是否删除成功
    """
    try:
        result = await db.execute(select(ContentBase).filter(ContentBase.id == content_id))
        content = result.scalars().first()
        
        if content:
            await db.delete(content)
            await db.commit()
            logger.info(f"删除知识库内容成功: {content_id}")
            return True
        return False
    except Exception as e:
        await db.rollback()
        logger.error(f"删除知识库内容失败: {e}")
        return False

async def create_directory(db: AsyncSession,kbf:FileDirectoryCreateDto) -> bool:
    """
    创建用户目录
    :param db:
    :param kbf:知识库路径构造
    :return:
    """
    db_directory = FileDirectory(
        title=kbf.title,
        parent_id=kbf.parent_id,
        user_id=kbf.user_id
    )
    db.add(db_directory)
    await db.commit()
    await db.refresh(db_directory)
    if db_directory:
        return True
    return False

async def get_directory_by_id(db: AsyncSession, directory_id: str) -> Optional[FileDirectory]:
    """
    根据ID获取目录
    """
    result = await db.execute(select(FileDirectory).filter(FileDirectory.id == directory_id))
    return result.scalars().first()

async def get_root_directories_by_user(db: AsyncSession, user_id: str) -> List[FileDirectory]:
    """
    获取用户的所有根目录（没有父级的目录）
    """
    result = await db.execute(
        select(FileDirectory)
        .filter(and_(FileDirectory.user_id == user_id, FileDirectory.parent_id.is_(None)))
        .order_by(FileDirectory.create_time)
    )
    return result.scalars().all()

async def get_directories_by_parent(db: AsyncSession, parent_id: str) -> List[FileDirectory]:
    """
    根据父级ID获取所有子目录
    """
    result = await db.execute(
        select(FileDirectory)
        .filter(FileDirectory.parent_id == parent_id)
        .order_by(FileDirectory.create_time)
    )
    return result.scalars().all()

async def get_directories_by_user(db: AsyncSession, user_id: str) -> List[FileDirectory]:
    """
    获取用户的所有目录
    """
    result = await db.execute(
        select(FileDirectory)
        .filter(FileDirectory.user_id == user_id)
        .order_by(FileDirectory.create_time)
    )
    return result.scalars().all()

async def update_directory(db: AsyncSession, directory_id: str,
                           directory_data: FileDirectoryUpdateDto) -> bool:
    """
    更新目录
    """
    try:
        result = await db.execute(select(FileDirectory).filter(FileDirectory.id == directory_id))
        db_directory = result.scalars().first()
        if db_directory:
            if directory_data.title is not None:
                db_directory.title = directory_data.title
            if directory_data.parent_id is not None:
                db_directory.parent_id = directory_data.parent_id

            await db.commit()
            await db.refresh(db_directory)
            return True
        return False
    except Exception as e:
        await db.rollback()
        return False

async def delete_directory(db: AsyncSession, directory_id: str) -> bool:
    """
    删除目录
    """
    result = await db.execute(select(FileDirectory).filter(FileDirectory.id == directory_id))
    db_directory = result.scalars().first()

    if db_directory:
        await db.delete(db_directory)
        await db.commit()
        return True
    return False

async def build_directory_tree(db: AsyncSession, user_id: str) -> List[dict]:
    """
    构建用户的完整目录树结构
    """
    # 获取用户的所有目录
    all_directories = await get_directories_by_user(db, user_id)

    # 创建一个字典，以目录ID为键，目录对象为值
    directory_dict = {directory.id: directory for directory in all_directories}

    # 创建一个字典，用于存储每个目录的子目录
    children_dict = {}
    for directory in all_directories:
        if directory.parent_id:
            if directory.parent_id not in children_dict:
                children_dict[directory.parent_id] = []
            children_dict[directory.parent_id].append(directory)
        else:
            if 'root' not in children_dict:
                children_dict['root'] = []
            children_dict['root'].append(directory)

    def build_tree(directory):
        """
        递归构建目录树
        """
        node = {
            "id": directory.id,
            "title": directory.title,
            "parent_id": directory.parent_id,
            "user_id": directory.user_id,
            "create_time": directory.create_time,
            "update_time": directory.update_time,
            "children": []
        }

        # 添加子目录
        if directory.id in children_dict:
            for child in children_dict[directory.id]:
                node["children"].append(build_tree(child))

        return node

    # 构建根目录树
    tree = []
    if 'root' in children_dict:
        for root_directory in children_dict['root']:
            tree.append(build_tree(root_directory))

    return tree