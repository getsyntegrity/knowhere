"""
Knowledge-base endpoints retained for the public API surface.
"""

from app.repositories.knowledge_base_repository import (
    create_directory,
    delete_directory,
    update_directory,
)
from app.services.rate_limit.dependencies import CurrentUser, with_current_user
from fastapi import APIRouter, Depends
from starlette import status

from shared.core.exceptions.domain_exceptions import KnowledgeBaseOperationException
from shared.models.schemas.files import (
    FileDirectoryCreateDto,
    FileDirectoryDto,
    FileDirectoryListDto,
    FileDirectoryUpdateDto,
)

router = APIRouter(tags=["Knowledge Base"])

# File-upload endpoints were removed. Use the unified /v1/jobs API instead.


# Directory management
@router.post(
    "/create_directory",
    status_code=status.HTTP_201_CREATED,
    summary="Create a directory",
    description="Create a directory for the current user's knowledge-base tree",
)
async def add_sql_path(
    request_data: FileDirectoryCreateDto,
    current_user: CurrentUser = Depends(with_current_user),
):
    """
    Create a directory entry in the knowledge-base tree.
    """
    try:
        request_data.user_id = current_user.user_id
        from shared.core.database import get_db_context

        async with get_db_context() as db:
            if await create_directory(db, request_data):
                return {"message": "Directory created"}
        raise KnowledgeBaseOperationException(
            internal_message="Failed to create directory"
        )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to create directory: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to create directory: {str(e)}"
        )


@router.post(
    "/delete_directory",
    status_code=status.HTTP_201_CREATED,
    summary="Delete a directory",
    description="Delete a directory from the current user's knowledge-base tree",
)
async def delete_sql_path(
    request_data: FileDirectoryDto,
    current_user: CurrentUser = Depends(with_current_user),
):
    """
    Delete a directory entry from the knowledge-base tree.
    """
    try:
        request_data.user_id = current_user.user_id
        from shared.core.database import get_db_context

        async with get_db_context() as db:
            if await delete_directory(db, request_data.id):
                return {"message": "Directory deleted"}
        raise KnowledgeBaseOperationException(
            internal_message="Failed to delete directory"
        )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to delete directory: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to delete directory: {str(e)}"
        )


@router.post(
    "/update_directory",
    status_code=status.HTTP_201_CREATED,
    summary="Update a directory",
    description="Update a directory in the current user's knowledge-base tree",
)
async def update_sql_path(
    request_data: FileDirectoryUpdateDto,
    current_user: CurrentUser = Depends(with_current_user),
):
    """
    Update a directory entry in the knowledge-base tree.
    """
    try:
        request_data.user_id = current_user.user_id
        from shared.core.database import get_db_context

        async with get_db_context() as db:
            if await update_directory(db, request_data):
                return {"message": "Directory updated"}
        raise KnowledgeBaseOperationException(
            internal_message="Failed to update directory"
        )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to update directory: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to update directory: {str(e)}"
        )


@router.post(
    "/get_directory",
    status_code=status.HTTP_201_CREATED,
    summary="Get the directory tree",
    description="Return the current user's knowledge-base directory tree",
)
async def get_sql_path(current_user: CurrentUser = Depends(with_current_user)):
    """
    Return the user's directory tree, creating a default root when needed.
    """
    try:
        from app.repositories.knowledge_base_repository import (
            create_directory,
            get_directories,
            get_directories_by_user,
        )

        from shared.core.database import get_db_context
        from shared.models.schemas.files import FileDirectoryCreateDto

        async with get_db_context() as db:
            # Load every directory owned by the current user.
            user_directories = await get_directories_by_user(db, current_user.user_id)

            # Create the default root when the user has no directories yet.
            if not user_directories:
                create_request = FileDirectoryCreateDto(
                    title="Default Directory",
                    parent_id=None,
                    user_id=current_user.user_id,
                )

                success = await create_directory(db, create_request)
                if not success:
                    from loguru import logger

                    logger.error(
                        f"Failed to create default directory: user_id={current_user.user_id}"
                    )
                    raise KnowledgeBaseOperationException(
                        internal_message="Failed to create default directory"
                    )

            # Return the hydrated directory tree.
            directories = await get_directories(db, current_user.user_id)
            return directories
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to load directory tree: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to get directory: {str(e)}"
        )


@router.post(
    "/list_directory",
    status_code=status.HTTP_201_CREATED,
    summary="List directory contents",
    description="Return knowledge-base content for the selected directory",
)
async def list_directory(
    request_data: FileDirectoryListDto,
    current_user: CurrentUser = Depends(with_current_user),
):
    """
    Return the knowledge-base content stored under one directory.
    """
    try:
        from app.repositories.knowledge_base_repository import get_directory_contents

        from shared.core.database import get_db_context

        async with get_db_context() as db:
            contents = await get_directory_contents(db, request_data.id)
            return contents
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to load directory contents: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to get directory contents: {str(e)}"
        )


# Add a knowledge-base path
@router.post(
    "/add_kb",
    status_code=status.HTTP_201_CREATED,
    summary="Add a knowledge-base path",
    description="Add a root knowledge-base path for the current user",
)
async def add_kb_path(
    request_data: dict, current_user: CurrentUser = Depends(with_current_user)
):
    """
    Add a knowledge-base path.
    """
    try:
        from app.repositories.knowledge_base_repository import create_directory

        from shared.core.database import get_db_context
        from shared.models.schemas.files import FileDirectoryCreateDto

        # Build the backing directory creation request.
        create_request = FileDirectoryCreateDto(
            title=request_data.get("path", ""),
            parent_id=None,  # Default to the root directory.
            user_id=current_user.user_id,
        )

        async with get_db_context() as db:
            success = await create_directory(db, create_request)
            if success:
                return {"message": "Knowledge-base path added"}
            else:
                raise KnowledgeBaseOperationException(
                    internal_message="Failed to add knowledge base path"
                )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to add knowledge-base path: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to add knowledge base path: {str(e)}"
        )


# Temporary file-upload endpoints were removed. Use /v1/jobs instead.

# The older synchronous endpoints below were removed in favor of /v1/jobs:
# - /add_kb_data
# - /add_kb_fragment
# - /search (removed; use the Worker-backed retrieval flow instead)
# - /get_kb_data
# - /delete_kb_data
# - /delete_kb
# - /encode_know
# - /get_fragments
# - /get_fileTree
# - /tree_kb
# - /forest_kb


# Delete knowledge-base content or directories
@router.delete(
    "/contents/{content_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete knowledge-base content or a directory",
    description="Delete content or a directory by ID",
)
async def delete_knowledge_content(
    content_id: str, current_user: CurrentUser = Depends(with_current_user)
):
    """
    Delete knowledge-base content or a directory.

    The route determines whether the ID points at content or a directory.
    """
    try:
        from app.repositories.knowledge_base_repository import (
            delete_directory,
            delete_kb_content,
        )
        from sqlalchemy import text

        from shared.core.database import get_db_context

        async with get_db_context() as db:
            # Check whether the ID belongs to a directory first.
            result = await db.execute(
                text("SELECT id FROM file_directory WHERE id = :id"), {"id": content_id}
            )
            is_directory = result.fetchone() is not None

            if is_directory:
                # Delete the directory.
                success = await delete_directory(db, content_id)
                if success:
                    return {"message": "Directory deleted"}
                else:
                    raise KnowledgeBaseOperationException(
                        internal_message="Failed to delete directory"
                    )
            else:
                # Delete the content row.
                success = await delete_kb_content(db, content_id)
                if success:
                    return {"message": "Content deleted"}
                else:
                    raise KnowledgeBaseOperationException(
                        internal_message="Failed to delete content"
                    )
    except KnowledgeBaseOperationException:
        raise
    except Exception as e:
        from loguru import logger

        logger.error(f"Failed to delete knowledge-base content: {e}")
        raise KnowledgeBaseOperationException(
            internal_message=f"Failed to delete knowledge base content: {str(e)}"
        )
