from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class FileDirectoryDto(BaseModel):
    """
    文件目录DTO，用于向前端传输目录结构数据
    """
    id: str
    title: str
    parent_id: Optional[str] = None
    user_id: str
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    children: List['FileDirectoryDto'] = []

    model_config = ConfigDict(from_attributes=True)


class FileDirectoryCreateDto(BaseModel):
    """
    创建文件目录的DTO
    """
    title: str
    parent_id: Optional[str] = None
    user_id: str

    model_config = ConfigDict(from_attributes=True)


class FileDirectoryUpdateDto(BaseModel):
    """
    更新文件目录的DTO
    """
    id: Optional[str] = None
    title: Optional[str] = None
    parent_id: Optional[str] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FileDirectoryListDto(BaseModel):
    """
    获取目录内容的DTO，只需要目录ID
    """
    id: str

    model_config = ConfigDict(from_attributes=True)


# 解决循环引用
FileDirectoryDto.model_rebuild()