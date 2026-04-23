"""S3 event schemas."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class S3Object(BaseModel):
    """S3 object metadata."""

    key: str = Field(..., description="S3 object key")
    size: Optional[int] = Field(None, description="Object size")
    eTag: Optional[str] = Field(None, description="ETag")
    sequencer: Optional[str] = Field(None, description="Sequencer value")


class S3Bucket(BaseModel):
    """S3 bucket metadata."""

    name: str = Field(..., description="Bucket name")
    arn: Optional[str] = Field(None, description="Bucket ARN")


class S3EventRecord(BaseModel):
    """One S3 event record."""

    eventVersion: str = Field(..., description="Event version")
    eventSource: str = Field(..., description="Event source")
    awsRegion: str = Field(..., description="AWS region")
    eventTime: str = Field(..., description="Event time")
    eventName: str = Field(..., description="Event name")
    userIdentity: Optional[Dict[str, Any]] = Field(None, description="User identity")
    requestParameters: Optional[Dict[str, Any]] = Field(None, description="Request parameters")
    responseElements: Optional[Dict[str, Any]] = Field(None, description="Response elements")
    s3: Dict[str, Any] = Field(..., description="S3 payload")

    # Parsed convenience fields.
    bucket_name: Optional[str] = Field(None, description="Bucket name")
    object_key: Optional[str] = Field(None, description="Object key")

    def __init__(self, **data):
        super().__init__(**data)
        # Parse the nested s3 payload into convenience fields.
        if self.s3:
            self.bucket_name = self.s3.get('bucket', {}).get('name')
            self.object_key = self.s3.get('object', {}).get('key')


class S3Event(BaseModel):
    """S3 event notification payload."""

    Records: List[S3EventRecord] = Field(..., description="Event records")

    def get_upload_events(self) -> List[S3EventRecord]:
        """Return only upload-related event records."""
        upload_events = []
        for record in self.Records:
            name = record.eventName or ""
            # Support the common upload event-name variants:
            # - ObjectCreated:Put / Post / CompleteMultipartUpload
            # - ObjectCreated:PutObject / PostObject (for OSS-to-S3 adaptation)
            # - prefixed names such as s3:ObjectCreated:PutObject
            if (
                "ObjectCreated" in name
                and (
                    "Put" in name
                    or "Post" in name
                    or "CompleteMultipartUpload" in name
                )
            ):
                upload_events.append(record)
        return upload_events
