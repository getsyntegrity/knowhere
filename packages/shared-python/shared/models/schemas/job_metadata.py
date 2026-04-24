"""Job metadata schemas."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobMetadataBase(BaseModel):
    """Base schema for stored job metadata."""

    # Core fields captured at creation time.
    original_request: Optional[Dict[str, Any]] = Field(
        None, description="Full JobCreate request payload"
    )
    parsing_params: Optional[Dict[str, Any]] = Field(
        None, description="Parsing parameters"
    )
    data_id: Optional[str] = Field(None, description="User-defined ID")
    webhook: Optional[Dict[str, Any]] = Field(None, description="Webhook configuration")
    # result_mode was removed and is no longer supported.

    # Source-file fields.
    source_type: Optional[str] = Field(None, description="Source type")
    source_file_name: Optional[str] = Field(None, description="Source file name")
    source_url: Optional[str] = Field(None, description="Source URL")
    file_url: Optional[str] = Field(None, description="File URL")

    # User config captured during creation.
    user_config: Optional[Dict[str, Any]] = Field(
        None, description="User configuration"
    )

    model_config = ConfigDict(extra="allow")


class JobMetadataHelper:
    """Helper methods for creating and reading job metadata."""

    @staticmethod
    def create_from_request(request, **kwargs) -> Dict[str, Any]:
        """Build metadata from a JobCreate request without embedding user_config."""
        metadata = {
            "original_request": request.model_dump(),
            "namespace": request.namespace or "default",
            "document_id": request.document_id,
            "parsing_params": (
                request.parsing_params.model_dump() if request.parsing_params else None
            ),
            "data_id": request.data_id,
            "webhook": request.webhook.model_dump() if request.webhook else None,
        }
        metadata.update(kwargs)
        return metadata

    @staticmethod
    def get_field(
        metadata: Optional[Dict[str, Any]], field: str, default: Any = None
    ) -> Any:
        """Safely read a field from metadata."""
        if not metadata:
            return default
        return metadata.get(field, default)

    @staticmethod
    def get_parsing_param(
        metadata: Optional[Dict[str, Any]], param: str, default: Any = None
    ) -> Any:
        """Read a value from parsing_params with backward compatibility."""
        if not metadata:
            return default

        parsing_params = metadata.get("parsing_params")
        if parsing_params and isinstance(parsing_params, dict):
            if param in parsing_params:
                return parsing_params.get(param, default)

        # Backward compatibility for older flat metadata layouts.
        if param in metadata:
            return metadata.get(param, default)

        return default

    @staticmethod
    def get_webhook(metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Return the webhook configuration from metadata."""
        return JobMetadataHelper.get_field(metadata, "webhook")
