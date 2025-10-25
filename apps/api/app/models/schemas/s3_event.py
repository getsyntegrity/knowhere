"""
S3事件相关Schema
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class S3Object(BaseModel):
    """S3对象信息"""
    key: str = Field(..., description="S3对象键")
    size: Optional[int] = Field(None, description="对象大小")
    eTag: Optional[str] = Field(None, description="ETag")
    sequencer: Optional[str] = Field(None, description="序列号")


class S3Bucket(BaseModel):
    """S3存储桶信息"""
    name: str = Field(..., description="存储桶名称")
    arn: Optional[str] = Field(None, description="存储桶ARN")


class S3EventRecord(BaseModel):
    """S3事件记录"""
    eventVersion: str = Field(..., description="事件版本")
    eventSource: str = Field(..., description="事件源")
    awsRegion: str = Field(..., description="AWS区域")
    eventTime: str = Field(..., description="事件时间")
    eventName: str = Field(..., description="事件名称")
    userIdentity: Optional[Dict[str, Any]] = Field(None, description="用户身份")
    requestParameters: Optional[Dict[str, Any]] = Field(None, description="请求参数")
    responseElements: Optional[Dict[str, Any]] = Field(None, description="响应元素")
    s3: Dict[str, Any] = Field(..., description="S3信息")
    
    # 解析后的字段
    bucket_name: Optional[str] = Field(None, description="存储桶名称")
    object_key: Optional[str] = Field(None, description="对象键")
    
    def __init__(self, **data):
        super().__init__(**data)
        # 解析s3字段
        if self.s3:
            self.bucket_name = self.s3.get('bucket', {}).get('name')
            self.object_key = self.s3.get('object', {}).get('key')


class S3Event(BaseModel):
    """S3事件通知"""
    Records: List[S3EventRecord] = Field(..., description="事件记录列表")
    
    def get_upload_events(self) -> List[S3EventRecord]:
        """获取文件上传事件"""
        upload_events = []
        for record in self.Records:
            if record.eventName in ['ObjectCreated:Put', 'ObjectCreated:Post', 'ObjectCreated:CompleteMultipartUpload']:
                upload_events.append(record)
        return upload_events
