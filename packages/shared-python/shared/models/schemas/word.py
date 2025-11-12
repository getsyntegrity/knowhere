from typing import Optional

from pydantic import BaseModel, Field


class FillTableDto(BaseModel):
    input_doc: Optional[str] = Field(..., description="输入的文档地址")
    output_doc: Optional[str] = Field(..., description="输出的文档地址")
class TaskDto(BaseModel):
    task_id: Optional[str] = Field(..., description="任务id")