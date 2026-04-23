from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from shared.core.database import Base
from datetime import datetime

def utc_now():
    return datetime.utcnow()


class ContentBase(Base):
    """Primary table for knowledge-base content."""
    __tablename__ = "knowledge_base"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()), comment="Content order identifier")
    content = Column(Text, nullable=True, comment="Content text")
    path = Column(Text, nullable=True, comment="File path or source")
    type = Column(String(2000), nullable=True, comment="Content type (for example PTXT or SUMMARY)")
    length = Column(Integer, nullable=True, comment="Content length or size")
    keywords = Column(String(511), nullable=True, comment="Content keywords")
    summary = Column(Text, nullable=True, comment="Content summary")
    know_id = Column(String(128), nullable=True, comment="Knowledge ID, possibly linked to an external knowledge base")
    tokens = Column(Text, nullable=True, comment="Tokenized content")
    embedding = Column(Text, nullable=True, comment="Content embedding for similarity search and related tasks")

class PathBase(Base):
    __tablename__ = "path_base"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()), comment="Path order identifier")
    path = Column(Text, nullable=True, comment="File path or source")
    embedding = Column(Text, nullable=True, comment="Content embedding for similarity search and related tasks")

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
    """Directory tree table for user files."""
    __tablename__ = "file_directory"
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()), comment="Directory unique identifier")
    title = Column(String(255), nullable=False, comment="Directory title")
    parent_id = Column(String(36), ForeignKey('file_directory.id'),nullable=True, comment="Parent directory ID; NULL indicates the root directory")
    user_id = Column(String(36), nullable=False, comment="Owning user ID")
    create_time = Column(DateTime, nullable=True, default=utc_now, comment="Creation time")
    update_time = Column(DateTime, nullable=True, default=utc_now, onupdate=utc_now, comment="Update time")

    # Self-referential relationship implemented through parent_id.
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
