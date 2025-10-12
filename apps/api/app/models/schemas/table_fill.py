"""
表格填充相关Schema
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class TableFillJobCreate(BaseModel):
    """创建表格填充任务请求"""
    source_type: str = Field(..., description="文件来源类型", pattern="^(direct_upload|url)$")
    file_path: Optional[str] = Field(None, description="文件路径（直传时使用）")
    file_url: Optional[str] = Field(None, description="文件URL（URL外链时使用）")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")


class TableFillJobResponse(BaseModel):
    """表格填充任务响应"""
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    current_state: Optional[str] = Field(None, description="当前详细状态")
    source_type: str = Field(..., description="文件来源类型")
    file_path: Optional[str] = Field(None, description="文件路径")
    s3_key: Optional[str] = Field(None, description="S3存储键")
    result_s3_key: Optional[str] = Field(None, description="结果文件S3键")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    webhook_enabled: bool = Field(False, description="是否启用Webhook")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class TableFillJobStatus(BaseModel):
    """表格填充任务状态"""
    job_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="顶层状态")
    current_state: Optional[str] = Field(None, description="当前详细状态")
    progress: Optional[Dict[str, Any]] = Field(None, description="进度信息")
    error_message: Optional[str] = Field(None, description="错误信息")
    result_s3_key: Optional[str] = Field(None, description="结果文件S3键")
    download_url: Optional[str] = Field(None, description="下载链接")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class TableFillJobList(BaseModel):
    """表格填充任务列表"""
    jobs: List[TableFillJobResponse] = Field(..., description="任务列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class TableFillUploadResponse(BaseModel):
    """表格填充文件上传响应"""
    job_id: str = Field(..., description="任务ID")
    upload_url: str = Field(..., description="上传URL")
    s3_key: str = Field(..., description="S3存储键")
    expires_in: int = Field(..., description="过期时间（秒）")


class TableFillDownloadResponse(BaseModel):
    """表格填充下载响应"""
    download_url: str = Field(..., description="下载URL")
    expires_in: int = Field(..., description="过期时间（秒）")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    content_type: Optional[str] = Field(None, description="文件类型")
