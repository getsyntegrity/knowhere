"""OSS event schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from shared.models.schemas.s3_event import S3Event, S3EventRecord


class OSSObject(BaseModel):
    """OSS object metadata."""

    key: str = Field(..., description="OSS object key")
    size: Optional[int] = Field(None, description="Object size")
    etag: Optional[str] = Field(None, description="ETag")
    sequencer: Optional[str] = Field(None, description="Sequencer value")


class OSSBucket(BaseModel):
    """OSS bucket metadata."""

    name: str = Field(..., description="Bucket name")
    arn: Optional[str] = Field(None, description="Bucket ARN")


class OSSEventRecord(BaseModel):
    """One OSS event record."""

    eventName: str = Field(
        ..., description="Event name, for example ObjectCreated:PutObject"
    )
    eventSource: str = Field(default="acs:oss", description="Event source")
    eventTime: str = Field(..., description="Event time")
    region: str = Field(..., description="OSS region")
    oss: Dict[str, Any] = Field(..., description="OSS payload")

    # Parsed convenience fields.
    bucket_name: Optional[str] = Field(None, description="Bucket name")
    object_key: Optional[str] = Field(None, description="Object key")

    def __init__(self, **data):
        super().__init__(**data)
        # Parse the nested oss payload into convenience fields.
        if self.oss:
            self.bucket_name = self.oss.get("bucket", {}).get("name")
            self.object_key = self.oss.get("object", {}).get("key")


class OSSEvent(BaseModel):
    """OSS event notification payload."""

    events: List[OSSEventRecord] = Field(..., description="Event records")

    def get_upload_events(self) -> List[OSSEventRecord]:
        """Return only upload-related event records."""
        upload_events = []
        for record in self.events:
            if record.eventName in [
                "ObjectCreated:PutObject",
                "ObjectCreated:PostObject",
                "ObjectCreated:CompleteMultipartUpload",
            ]:
                upload_events.append(record)
        return upload_events

    def to_s3_event(self) -> S3Event:
        """
        Convert the OSS event payload into an S3Event payload.

        This allows the existing S3 event-processing logic to be reused.
        """
        s3_records = []
        for oss_record in self.events:
            # Convert each OSS record into S3EventRecord shape.
            s3_record = S3EventRecord(
                eventVersion="2.1",
                eventSource="oss:event",
                awsRegion=oss_record.region,
                eventTime=oss_record.eventTime,
                eventName=oss_record.eventName.replace(
                    "ObjectCreated:", "s3:ObjectCreated:"
                ).replace("ObjectRemoved:", "s3:ObjectRemoved:"),
                s3={
                    "bucket": {
                        "name": oss_record.bucket_name,
                        "arn": f"oss://{oss_record.bucket_name}",
                    },
                    "object": {
                        "key": oss_record.object_key,
                        "size": oss_record.oss.get("object", {}).get("size"),
                        "eTag": oss_record.oss.get("object", {}).get("etag"),
                    },
                },
                bucket_name=oss_record.bucket_name,
                object_key=oss_record.object_key,
            )
            s3_records.append(s3_record)

        return S3Event(Records=s3_records)
