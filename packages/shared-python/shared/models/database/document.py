"""Canonical retrieval-serving document state models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.core.database import Base


class Document(Base):
    """Durable user document in a retrieval namespace."""

    __tablename__ = 'documents'

    document_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: f'doc_{uuid4().hex[:12]}')
    user_id: Mapped[str] = mapped_column(Text, ForeignKey('user.id', ondelete='RESTRICT'), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False, default='default')
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='active')
    current_job_result_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('job_results.id', ondelete='SET NULL'), nullable=True)
    source_file_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    sections: Mapped[List['DocumentSection']] = relationship('DocumentSection', back_populates='document', cascade='all, delete-orphan', lazy='noload')
    chunks: Mapped[List['DocumentChunk']] = relationship('DocumentChunk', back_populates='document', cascade='all, delete-orphan', lazy='noload')

    __table_args__ = (
        Index('idx_documents_user_namespace_status', 'user_id', 'namespace', 'status'),
        Index('idx_documents_current_job_result', 'current_job_result_id'),
    )


class DocumentSection(Base):
    """Canonical hierarchy node for one published document revision."""

    __tablename__ = 'document_sections'

    section_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: f'sec_{uuid4().hex[:12]}')
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False, default='default')
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey('documents.document_id', ondelete='CASCADE'), nullable=False)
    job_result_id: Mapped[str] = mapped_column(String(36), ForeignKey('job_results.id', ondelete='CASCADE'), nullable=False)
    parent_section_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('document_sections.section_id', ondelete='SET NULL'), nullable=True)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    section_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    section_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped[Document] = relationship('Document', back_populates='sections')

    __table_args__ = (
        UniqueConstraint('document_id', 'job_result_id', 'section_path', name='uq_document_sections_revision_path'),
        Index('idx_document_sections_scope', 'user_id', 'namespace'),
        Index('idx_document_sections_doc_revision', 'document_id', 'job_result_id'),
    )


class DocumentChunk(Base):
    """Canonical retrieval payload row for one published document revision."""

    __tablename__ = 'document_chunks'

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False, default='default')
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey('documents.document_id', ondelete='CASCADE'), nullable=False)
    job_result_id: Mapped[str] = mapped_column(String(36), ForeignKey('job_results.id', ondelete='CASCADE'), nullable=False)
    section_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey('document_sections.section_id', ondelete='SET NULL'), nullable=True)
    chunk_type: Mapped[str] = mapped_column(String(64), nullable=False, default='text')
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_chunk_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped[Document] = relationship('Document', back_populates='chunks')

    __table_args__ = (
        UniqueConstraint('document_id', 'job_result_id', 'source_chunk_path', name='uq_document_chunks_revision_path'),
        Index('idx_document_chunks_scope', 'user_id', 'namespace'),
        Index('idx_document_chunks_doc_revision', 'document_id', 'job_result_id'),
        Index('idx_document_chunks_section', 'section_id'),
    )
