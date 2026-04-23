from typing import List, Optional

from shared.core.database import get_db_context
from shared.models.database.knowledge_base import (ContentBase, FileDirectory,
                                                KBPydantic, PathBase,
                                                PathPydantic)
from shared.models.schemas.files import (FileDirectoryCreateDto, FileDirectoryUpdateDto)
from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_update_kb(kbs: list[KBPydantic], db: AsyncSession = None) -> bool:
    """
    Create or update knowledge-base content.

    :param kbs: Vector Objects
    :param db: Optional external database session. If provided, transaction is NOT committed here.
    :return: Success boolean
    """
    if not kbs:
        return True
    
    # Object mapping
    object_mappings = []
    for kb in kbs:
        data_dict = kb.model_dump()
        processed_dict = {
            key: (value if value is not None else '')
            for key, value in data_dict.items()
        }
        object_mappings.append(processed_dict)
        
    try:
        if db:
            # Use provided session, do not commit
            await db.run_sync(
                lambda session: session.bulk_insert_mappings(ContentBase, object_mappings)
            )
            # Flush to ensure constraints are checked, but don't commit
            await db.flush()
            logger.info(f"Bulk inserted {len(object_mappings)} records (Session Flush)")
            return True
        else:
            # Use internal session management
            async with get_db_context() as session:
                await session.run_sync(
                    lambda s: s.bulk_insert_mappings(ContentBase, object_mappings)
                )
                await session.commit()
                logger.info(f"Bulk inserted {len(object_mappings)} records (Committed)")
                return True
                
    except Exception as e:
        logger.error(f"Error bulk inserting records: {e}")
        if not db: # Only catch/rollback if we own the session
             # Context manager handles rollback for critical errors, but safe to log
             pass
        # Propagate error if external session (let caller handle rollback)
        if db:
            raise e
        return False

async def create_update_path(paths:list[PathPydantic]) -> bool:
    """
    Create or update knowledge-base paths.

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
    Get a knowledge base by ID.

    :param kb_id:
    :return:
    """

async def get_directories(db: AsyncSession, user_id: str) -> List[dict]:
    """
    Get the directory-tree structure for a user.

    :param db: Database session.
    :param user_id: User ID.
    :return: Directory-tree structure list.
    """
    return await build_directory_tree(db, user_id)

async def get_directory_contents(db: AsyncSession, directory_id: str) -> List[dict]:
    """
    Get knowledge-base content under a directory ID.

    :param db: Database session.
    :param directory_id: Directory ID.
    :return: Knowledge-base content list.
    """
    try:
        # Load the directory first.
        directory = await get_directory_by_id(db, directory_id)
        if not directory:
            return []
        
        # Match related content by the directory title in the ContentBase path.
        # Prefix format: {kb_dir};{document_name};{section}
        split_char = ";"
        directory_prefix = directory.title + split_char
        result = await db.execute(
            select(ContentBase)
            .filter(ContentBase.path.startswith(directory_prefix))
            .order_by(ContentBase.id)
        )
        contents = result.scalars().all()
        
        # Convert ORM rows to dictionaries.
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
    Delete knowledge-base content by content ID.

    :param db: Database session.
    :param content_id: Content ID.
    :return: Whether deletion succeeded.
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
    Create a user directory.

    :param db:
    :param kbf: Knowledge-base path payload.
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
    Get a directory by ID.
    """
    result = await db.execute(select(FileDirectory).filter(FileDirectory.id == directory_id))
    return result.scalars().first()

async def get_root_directories_by_user(db: AsyncSession, user_id: str) -> List[FileDirectory]:
    """
    Get all root directories for a user.
    """
    result = await db.execute(
        select(FileDirectory)
        .filter(and_(FileDirectory.user_id == user_id, FileDirectory.parent_id.is_(None)))
        .order_by(FileDirectory.create_time)
    )
    return result.scalars().all()

async def get_directories_by_parent(db: AsyncSession, parent_id: str) -> List[FileDirectory]:
    """
    Get all child directories by parent ID.
    """
    result = await db.execute(
        select(FileDirectory)
        .filter(FileDirectory.parent_id == parent_id)
        .order_by(FileDirectory.create_time)
    )
    return result.scalars().all()

async def get_directories_by_user(db: AsyncSession, user_id: str) -> List[FileDirectory]:
    """
    Get all directories for a user.
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
    Update a directory.
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
    Delete a directory.
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
    Build the full directory tree for a user.
    """
    # Load all directories for the user.
    all_directories = await get_directories_by_user(db, user_id)

    # Build a dictionary keyed by directory ID.
    directory_dict = {directory.id: directory for directory in all_directories}

    # Build a dictionary that stores children for each directory.
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
        Recursively build the directory tree.
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

        # Attach child directories.
        if directory.id in children_dict:
            for child in children_dict[directory.id]:
                node["children"].append(build_tree(child))

        return node

    # Build the root directory tree.
    tree = []
    if 'root' in children_dict:
        for root_directory in children_dict['root']:
            tree.append(build_tree(root_directory))

    return tree
