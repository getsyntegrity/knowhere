"""Knowledge-base DTOs."""
from typing import List, Optional

from pydantic import BaseModel, Field


class AddKBPath(BaseModel):
    path: str = Field(..., description="Path")
    label: list[str] = Field(..., description="Labels")


class AddKBDataSingle(BaseModel):
    """Add a single file to a knowledge base.

    Multiple-file or directory ingestion can be modeled as repeated calls to
    this DTO.
    """

    kb_path: str = Field(..., description="Knowledge-base path")
    user_id: str = Field(..., description="User ID")
    doc_type: str = Field(default="general", description="Document type")
    smart_title_parse: bool = Field(..., description="Enable smart hierarchy parsing")
    summary_image: bool = Field(
        ...,
        description="Use an LLM to summarize images, which adds the most extra time and token cost",
    )
    summary_table: bool = Field(
        ...,
        description="Use an LLM to summarize tables, which adds a small extra time and token cost",
    )
    summary_txt: bool = Field(
        ...,
        description="Use an LLM to summarize text and keywords, which adds a small extra time and token cost",
    )
    file_url: Optional[str] = Field(
        ...,
        description="File URL or path list to add to the knowledge base",
    )
    add_frag_desc: Optional[str] = Field(
        None,
        description="Manual description for fragment knowledge such as images",
    )


class GetKBData(BaseModel):
    kb_path: str = Field(..., description="Knowledge-base path")
    user_id: str = Field(..., description="User ID")


class DelKB(BaseModel):
    remove_node: str = Field(..., description="Knowledge node to remove")


class AddKBFragment(BaseModel):
    kb_path: str = Field(..., description="Knowledge-base path")
    fragment_content: Optional[str] = Field(
        ...,
        description="Fragment content to add to the knowledge base, such as a paragraph",
    )
    fragment_title: Optional[str] = Field(
        ...,
        description="Fragment title, if one is not extracted automatically by an LLM",
    )
    smart_title_parse: bool = Field(..., description="Enable smart hierarchy parsing")
    summary_image: bool = Field(
        ...,
        description="Use an LLM to summarize images, which adds the most extra time and token cost",
    )
    summary_txt: bool = Field(
        ...,
        description="Use an LLM to summarize text and keywords, which adds a small extra time and token cost",
    )
    summary_table: bool = Field(
        ...,
        description="Use an LLM to summarize tables, which adds a small extra time and token cost",
    )
    add_frag_desc: Optional[str] = Field(
        None,
        description="Manual description for fragment knowledge such as images",
    )
    label: Optional[str] = Field(..., description="Label")


class EncodeKnow(BaseModel):
    kb_path: str = Field(..., description="Knowledge-base path")


class GetKBFragment(BaseModel):
    kb_path: str = Field(..., description="Knowledge-base path")


class Ask(BaseModel):
    question: str = Field(..., description="User question")
    context: str = Field(..., description="Context returned by RAG")


class SearchAsk(BaseModel):
    question: str = Field(..., description="User question")
    topk: int = Field(default=3, description="Default number of knowledge fragments to return")
    filter_nodes: List[str] = Field(..., description="Knowledge-base paths to exclude or keep")
    filter_mode: str = Field(..., description="Knowledge-base filtering mode")
    filter_type: int = Field(default=1, description="Knowledge-base filter data type")
    show_image: bool = Field(..., description="Show images")
    rerank: bool = Field(..., description="Enable reranking")
    ask: bool = Field(..., description="Ask directly against the recalled results")
    ask_multimodal: bool = Field(..., description="Enable multimodal question answering")
    ask_agent: bool = Field(
        ...,
        description="Enable deep-research self-checking, query enhancement, advanced table analysis, and self-training features",
    )


class BuildTree(BaseModel):
    smart_summary: bool = Field(default=True, description="Enable smart recursive summaries")
    root_node: str = Field(..., description="Document data node to organize into a tree")


class BuildForest(BaseModel):
    cut_len: int = Field(
        default=2000,
        description="Truncate the source content when a node has no summary and exceeds this threshold",
    )
    k: int = Field(default=5, description="Number of most-similar nodes to cover per pass")
    threshold: float = Field(default=0.8, description="Minimum similarity threshold for node association")
    source_node: str = Field(
        ...,
        description="Source node to associate with the rest of the knowledge base",
    )
