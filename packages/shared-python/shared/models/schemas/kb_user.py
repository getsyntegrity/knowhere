"""Frontend-facing knowledge-base schema models."""
from typing import List

from pydantic import BaseModel, Field


class FragmentBean(BaseModel):
    data_type: int = Field(..., description="Data type")
    fragments: str = Field(..., description="Fragment content")
    labels: list[str] = Field(..., description="Labels")


class FileTreeBean(BaseModel):
    name: str = Field(..., description="Knowledge node name")
    id: str = Field(..., description="Knowledge node ID")
    content: str = Field(..., description="Node content")
    resource: list[object] = Field(..., description="Attached resources")
    children: List["FileTreeBean"] = Field(..., description="Child nodes")

    model_config = {
        "arbitrary_types_allowed": True,
    }

class AddKBPathModels(BaseModel):
    path: str = Field(..., description="Knowledge-base path")


class GetFragmentsModels(BaseModel):
    count: int = Field(..., description="Fragment count")
    kb_fragment: list[FragmentBean] = Field(..., description="Fragments")


class FileTreeModels(BaseModel):
    file_tree: list[FileTreeBean] = Field(..., description="File tree")
