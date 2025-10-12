"""
用户知识库相关的前端models
代码上方为基础bean
"""
from typing import List
from pydantic import BaseModel, Field


class FragmentBean(BaseModel):
   data_type: int = Field(..., description="数据类型")
   fragments:str = Field(..., description="碎片")
   labels:list[str] = Field(..., description="标签")

class FileTreeBean(BaseModel):
    name: str = Field(..., description="知识点名称")
    id: str = Field(..., description="知识id")
    content: str = Field(..., description="内容")
    resource:list[object] = Field(..., description="资源")
    children: List['FileTreeBean'] = Field(..., description="子节点")

    model_config = {
        "arbitrary_types_allowed": True
    }





class AddKBPathModels(BaseModel):
    path: str = Field(..., description="路径")

class GetFragmentsModels(BaseModel):
    count:int = Field(..., description="碎片数量")
    kb_fragment:list[FragmentBean] = Field(..., description="碎片列表")
class FileTreeModels(BaseModel):
    file_tree: list[FileTreeBean] = Field(..., description="文件树")









