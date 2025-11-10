from typing import Optional, List
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, Integer, LargeBinary, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped

from app.core.database import Base
from app.models.database.user import utc_now


class ContentBase(Base):
    """
    知识库内容主表
    """
    __tablename__ = "knowledge_base"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()), comment="内容顺序标识符")
    content = Column(Text, nullable=True, comment="内容的具体文本")
    path = Column(Text, nullable=True, comment="文件路径或来源")
    type = Column(String(2000), nullable=True, comment="内容类型（如PTXT, SUMMARY等）")
    length = Column(Integer, nullable=True, comment="内容的长度或大小")
    keywords = Column(String(511), nullable=True, comment="内容的关键词")
    summary = Column(Text, nullable=True, comment="内容的摘要")
    know_id = Column(String(128), nullable=True, comment="知识ID，可能关联到外部知识库")
    tokens = Column(Text, nullable=True, comment="内容分词后的token")
    embedding = Column(Text, nullable=True, comment="内容的语义向量，用于相似度搜索等")

class PathBase(Base):
    __tablename__ = "path_base"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()), comment="路径顺序标识符")
    path = Column(Text, nullable=True, comment="文件路径或来源")
    embedding = Column(Text, nullable=True, comment="内容的语义向量，用于相似度搜索等")

class KBPydantic(BaseModel):
    content:Optional[str] = None
    path:Optional[str] = None
    type:Optional[str] = None
    length:Optional[int] = None
    keywords:Optional[str] = None
    summary:Optional[str] = None
    know_id:Optional[str] = None
    tokens:Optional[str] = None
    embedding:Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
class PathPydantic(BaseModel):
    path:Optional[str] = None
    embedding:Optional[bytes] = None
    model_config = ConfigDict(from_attributes=True)


class FileDirectory(Base):
    """
    用户文件目录结构表
    """
    __tablename__ = "file_directory"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()), comment="目录唯一标识符")
    title = Column(String(255), nullable=False, comment="目录标题")
    parent_id = Column(String(36), ForeignKey('file_directory.id'),nullable=True, comment="父级目录ID，NULL表示根目录")
    user_id = Column(String(36), nullable=False, comment="所属用户ID")
    create_time = Column(DateTime, nullable=True, default=utc_now, comment="创建时间")
    update_time = Column(DateTime, nullable=True, default=utc_now, onupdate=utc_now, comment="更新时间")

    # 通过parent_id实现自引用关系
    parent: Mapped["FileDirectory"] = relationship(
        "FileDirectory",
        remote_side=[id],
        back_populates="children"
    )
    children: Mapped[List["FileDirectory"]] = relationship(
        "FileDirectory",
        back_populates="parent"
    )

    def __repr__(self):
        return f"<FileDirectory(id={self.id}, title='{self.title}', parent_id={self.parent_id})>"