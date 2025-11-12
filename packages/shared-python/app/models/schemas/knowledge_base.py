
"""
知识库相关的DTO
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class AddKBPath(BaseModel):
    path: str = Field(..., description="路径")
    label: list[ str] = Field(..., description="标签")

class AddKBDataSingle(BaseModel):
    '''
        该函数只实现了单个文件加入知识库 需要考虑一组文件或者扫描一个文件夹内加入知识库 是对该函数的多次调用
    '''
    kb_path: str = Field(..., description="知识库路径")
    user_id: str = Field(..., description="用户名")
    doc_type: str = Field(description="文件类型", default="general")
    smart_title_parse: bool = Field(..., description="是否启用智能层级解析")
    summary_image: bool = Field(..., description="是否使用大模型提炼图像（会费最多的额外时间和tokens）")
    summary_table: bool = Field(..., description="是否使用大模型提炼表格（会费少量额外时间和tokens）")
    summary_txt: bool = Field(..., description="是否使用大模型提炼文本内容和关键词（会费少量额外时间和tokens）")
    file_url:Optional[str] = Field(...,description="待加入知识库的文件url或路径列表")
    add_frag_desc:Optional[str] = Field(None, description="针对碎片知识（如图片）的人工增加的描述")

class GetKBData(BaseModel):
    kb_path: str = Field(..., description="知识库路径")
    user_id: str = Field(..., description="用户id")

class DelKB(BaseModel):
    remove_node: str = Field(..., description="被删除的知识节点")

class AddKBFragment(BaseModel):
    kb_path: str = Field(..., description="知识库路径")
    fragment_content: Optional[str] = Field(..., description="待加入知识库的碎片资料（比如一段话）")
    fragment_title: Optional[str] = Field(..., description="碎片资料题目（如果没有大模型可自动提取）")
    smart_title_parse: bool = Field(..., description="是否启用智能层级解析")
    summary_image: bool = Field(..., description="是否使用大模型提炼图像（会费最多的额外时间和tokens）")
    summary_txt: bool = Field(..., description="是否使用大模型提炼文本内容和关键词（会费少量额外时间和tokens）")
    summary_table: bool = Field(..., description="是否使用大模型提炼表格（会费少量额外时间和tokens）")
    add_frag_desc: Optional[str] = Field(None, description="针对碎片知识（如图片）的人工增加的描述")
    label: Optional[str] = Field(..., description="标签")

class EncodeKnow(BaseModel):
    kb_path: str = Field(..., description="知识库路径")

class  GetKBFragment(BaseModel):
    kb_path: str = Field(..., description="知识库路径")

class Ask(BaseModel):
    question: str = Field(..., description="用户问题")
    context: str = Field(..., description="RAG返回的上下文")

class SearchAsk(BaseModel):
    question: str = Field(..., description="用户问题")
    topk: int = Field(description="默认返回的知识片段数量", default=3)
    filter_nodes: List[str] = Field(..., description="过滤或仅保留的知识库路径")
    filter_mode: str = Field(..., description="知识库筛选模式")
    filter_type: int = Field(description="知识库筛选数据类型", default=1)
    show_image: bool = Field(..., description="是否展示图片")
    rerank: bool = Field(..., description="重排序方法")
    ask: bool = Field(..., description="是否直接基于召回结果提问")
    ask_multimodal: bool = Field(..., description="是否启动多模态问答") # 收费
    ask_agent: bool = Field(..., description="是否启动 deep research 自检查和查询增强 表格高级分析 自训练 等功能") # 收费

class BuildTree(BaseModel):
    smart_summary:bool = Field(description="是否启动智能递归摘要", default=True)
    root_node: str = Field(..., description="要进行树形归纳的文档数据节点")

class BuildForest(BaseModel):
    cut_len: int = Field(description="当节点没有summary且本体内容超过该阈值会截断", default=2000)
    k: int = Field(description="每次覆盖多少个最相似的节点", default=5)
    threshold: float = Field(description="节点关联的最低相似度阈值", default=0.8)
    source_node: str = Field(..., description="要和其余知识库部分进行关联的source节点")