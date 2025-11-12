"""
统一Job相关Schema（符合PRD规范）
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class WebhookConfig(BaseModel):
    """Webhook配置"""

    url: str = Field(..., description="Webhook回调URL")
    secret: str = Field(..., description="用于生成签名的密钥")
    
class ParsingParams(BaseModel):
    """解析参数"""
    model: Literal["base", "advanced"] = Field("base", description="使用的模型")
    ocr_enabled: bool = Field(False, description="是否启用OCR")
    kb_dir: Optional[str] = Field("默认目录", description="知识库目录")
    doc_type: Literal["auto", "pdf", "docx", "txt", "md"] = Field("auto", description="文档类型")
    smart_title_parse: bool = Field(True, description="智能标题解析")
    summary_image: bool = Field(True, description="是否生成图片摘要")
    summary_table: bool = Field(True, description="是否生成表格摘要")
    summary_txt: bool = Field(True, description="是否生成文本摘要")
    add_frag_desc: Optional[str] = Field("", description="添加片段描述")


class JobCreate(BaseModel):
    """创建任务请求"""

    source_type: Literal["file", "url"] = Field(..., description="文档来源类型")
    source_url: Optional[str] = Field(
        None, description="文件URL（source_type=url时必填）"
    )
    file_name: Optional[str] = Field(
        None, description="文件名（source_type=file时必填，需包含扩展名）"
    )
    data_id: Optional[str] = Field(None, max_length=128, description="用户自定义ID")
    parsing_params: Optional[ParsingParams] = Field(None, description="解析参数")
    webhook: Optional[WebhookConfig] = Field(None, description="Webhook配置")


class JobResponse(BaseModel):
    """任务响应"""

    job_id: str = Field(..., description="任务ID")
    status: Literal["pending", "waiting-file", "running", "converting", "done", "failed"] = Field(..., description="任务状态")
    source_type: str = Field(..., description="文件来源类型")
    data_id: Optional[str] = Field(None, description="用户自定义ID")
    created_at: datetime = Field(..., description="创建时间")

    # waiting-file状态特有字段
    upload_url: Optional[str] = Field(None, description="上传URL")
    upload_headers: Optional[Dict[str, str]] = Field(None, description="上传请求头")
    expires_in: Optional[int] = Field(None, description="URL过期时间（秒）")


class JobResult(BaseModel):
    """任务状态查询响应"""

    job_id: str = Field(..., description="任务ID")
    status: Literal["pending", "waiting-file", "running", "converting", "done", "failed"] = Field(..., description="任务状态")
    source_type: str = Field(..., description="文件来源类型")
    data_id: Optional[str] = Field(None, description="用户自定义ID")
    created_at: datetime = Field(..., description="创建时间")

    # 状态相关字段
    progress: Optional[Dict[str, Any]] = Field(None, description="进度信息")
    error: Optional[Dict[str, Any]] = Field(None, description="错误信息")

    # 结果相关字段
    result: Optional[Dict[str, Any]] = Field(None, description="解析结果（包含 checksum 和 statistics）")
    result_url: Optional[str] = Field(None, description="结果文件URL（ZIP包下载链接）")
    result_url_expires_at: datetime = Field(..., description="结果文件URL过期时间")


class JobList(BaseModel):
    """任务列表响应"""

    jobs: list[JobResult] = Field(..., description="任务列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class ConfirmUploadRequest(BaseModel):
    """确认上传请求"""

    pass  # 无需额外参数，从URL路径获取job_id
