"""JSON serialization with version markers."""

import json
from typing import Any

from pydantic import BaseModel

from canonical.exceptions import SerializationError


class JsonSerializer:
    """Lossless JSON serialization/deserialization with version markers."""
    
    CURRENT_VERSION = "1.0.0"
    
    def to_json(self, entity: BaseModel) -> str:
        """Serialize entity to JSON string with version marker."""
        data = entity.model_dump(mode="json")
        data["canonical_model_version"] = self.CURRENT_VERSION
        return json.dumps(data, indent=2)
    
    def from_json(self, json_str: str, entity_type: type[BaseModel]) -> BaseModel:
        """Deserialize JSON string to entity with version validation."""
        data = json.loads(json_str)
        
        version = data.pop("canonical_model_version", None)
        if version is None:
            raise SerializationError("Missing canonical_model_version in serialized data")
        
        # Validate major version
        major_version = version.split(".")[0]
        current_major = self.CURRENT_VERSION.split(".")[0]
        if major_version != current_major:
            raise SerializationError(
                f"Major version mismatch: {version} vs {self.CURRENT_VERSION}",
                version=version,
            )
        
        # Minor version differences are forward-compatible
        return entity_type.model_validate(data)
    
    def to_json_collection(self, entities: list[BaseModel]) -> str:
        """Serialize a collection of entities."""
        data = {
            "canonical_model_version": self.CURRENT_VERSION,
            "entities": [e.model_dump(mode="json") for e in entities],
        }
        return json.dumps(data, indent=2)
    
    def from_json_collection(self, json_str: str, entity_types: dict[str, type[BaseModel]]) -> list[BaseModel]:
        """Deserialize a collection of entities."""
        data = json.loads(json_str)
        
        version = data.pop("canonical_model_version", None)
        if version is None:
            raise SerializationError("Missing canonical_model_version in serialized data")
        
        major_version = version.split(".")[0]
        current_major = self.CURRENT_VERSION.split(".")[0]
        if major_version != current_major:
            raise SerializationError(
                f"Major version mismatch: {version} vs {self.CURRENT_VERSION}",
                version=version,
            )
        
        result = []
        for entity_data in data.get("entities", []):
            # Entity type must be inferred from the data structure
            # This is a simplified version; real implementation would use type discriminators
            result.append(entity_data)
        
        return result
