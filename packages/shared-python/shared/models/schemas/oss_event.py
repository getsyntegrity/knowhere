"""
OSS事件相关Schema
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from shared.models.schemas.s3_event import S3Event, S3EventRecord


class OSSObject(BaseModel):
    """OSS对象信息"""
    key: str = Field(..., description="OSS对象键")
    size: Optional[int] = Field(None, description="对象大小")
    etag: Optional[str] = Field(None, description="ETag")
    sequencer: Optional[str] = Field(None, description="序列号")


class OSSBucket(BaseModel):
    """OSS存储桶信息"""
    name: str = Field(..., description="存储桶名称")
    arn: Optional[str] = Field(None, description="存储桶ARN")


class OSSEventRecord(BaseModel):
    """OSS事件记录"""
    eventName: str = Field(..., description="事件名称，如 ObjectCreated:PutObject")
    eventSource: str = Field(default="acs:oss", description="事件源")
    eventTime: str = Field(..., description="事件时间")
    region: str = Field(..., description="OSS区域")
    oss: Dict[str, Any] = Field(..., description="OSS信息")
    
    # 解析后的字段
    bucket_name: Optional[str] = Field(None, description="存储桶名称")
    object_key: Optional[str] = Field(None, description="对象键")
    
    def __init__(self, **data):
        super().__init__(**data)
        # 解析oss字段
        if self.oss:
            self.bucket_name = self.oss.get('bucket', {}).get('name')
            self.object_key = self.oss.get('object', {}).get('key')


class OSSEvent(BaseModel):
    """OSS事件通知"""
    events: List[OSSEventRecord] = Field(..., description="事件记录列表")
    
    def get_upload_events(self) -> List[OSSEventRecord]:
        """获取文件上传事件"""
        upload_events = []
        for record in self.events:
            if record.eventName in ['ObjectCreated:PutObject', 'ObjectCreated:PostObject', 
                                   'ObjectCreated:CompleteMultipartUpload']:
                upload_events.append(record)
        return upload_events
    
    def to_s3_event(self) -> S3Event:
        """
        将OSS事件转换为S3Event格式
        以便复用现有的S3事件处理逻辑
        """
        s3_records = []
        for oss_record in self.events:
            # 转换为S3EventRecord格式
            s3_record = S3EventRecord(
                eventVersion="2.1",
                eventSource="oss:event",
                awsRegion=oss_record.region,
                eventTime=oss_record.eventTime,
                eventName=oss_record.eventName.replace('ObjectCreated:', 's3:ObjectCreated:').replace('ObjectRemoved:', 's3:ObjectRemoved:'),
                s3={
                    'bucket': {
                        'name': oss_record.bucket_name,
                        'arn': f"oss://{oss_record.bucket_name}"
                    },
                    'object': {
                        'key': oss_record.object_key,
                        'size': oss_record.oss.get('object', {}).get('size'),
                        'eTag': oss_record.oss.get('object', {}).get('etag')
                    }
                },
                bucket_name=oss_record.bucket_name,
                object_key=oss_record.object_key
            )
            s3_records.append(s3_record)
        
        return S3Event(Records=s3_records)

