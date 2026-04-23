from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class FileDirectoryDto(BaseModel):
    """Directory DTO used to return the directory tree to clients."""

    id: str
    title: str
    parent_id: Optional[str] = None
    user_id: str
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    children: List['FileDirectoryDto'] = []

    model_config = ConfigDict(from_attributes=True)


class FileDirectoryCreateDto(BaseModel):
    """DTO for creating a directory."""

    title: str
    parent_id: Optional[str] = None
    user_id: str

    model_config = ConfigDict(from_attributes=True)


class FileDirectoryUpdateDto(BaseModel):
    """DTO for updating a directory."""

    id: Optional[str] = None
    title: Optional[str] = None
    parent_id: Optional[str] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FileDirectoryListDto(BaseModel):
    """DTO for listing directory contents; only the directory ID is required."""

    id: str

    model_config = ConfigDict(from_attributes=True)


# Resolve the self-referential FileDirectoryDto annotation.
FileDirectoryDto.model_rebuild()
