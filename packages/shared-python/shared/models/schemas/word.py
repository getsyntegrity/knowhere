from typing import Optional

from pydantic import BaseModel, Field


class FillTableDto(BaseModel):
    input_doc: Optional[str] = Field(..., description="Input document path")
    output_doc: Optional[str] = Field(..., description="Output document path")


class TaskDto(BaseModel):
    task_id: Optional[str] = Field(..., description="Task ID")
