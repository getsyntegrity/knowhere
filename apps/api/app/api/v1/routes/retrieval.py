"""Retrieval API routes for lexical + graph-routing baseline."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rate_limit.dependencies import CurrentUser, with_current_user
from shared.core.database import get_db
from shared.services.retrieval import run_retrieval_query

router = APIRouter(tags=["Retrieval"])


class ExcludeSection(BaseModel):
    document_id: str
    section_path: str


class RetrievalQueryRequest(BaseModel):
    namespace: str | None = Field(None, description="Effective namespace; defaults to default")
    query: str
    top_k: int = 10
    exclude_document_ids: list[str] = Field(default_factory=list)
    exclude_sections: list[ExcludeSection] = Field(default_factory=list)


@router.post('/query')
async def query_retrieval(
    payload: RetrievalQueryRequest,
    current_user: CurrentUser = Depends(with_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await run_retrieval_query(
        db=db,
        user_id=current_user.user_id,
        namespace=payload.namespace or 'default',
        query=payload.query,
        top_k=payload.top_k,
        exclude_document_ids=payload.exclude_document_ids,
        exclude_sections=[item.model_dump() for item in payload.exclude_sections],
    )
