"""Canonical model error types."""


class CanonicalError(Exception):
    """Base error for all canonical model operations."""
    
    def __init__(self, message: str, code: str = "CANONICAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class InvariantViolation(CanonicalError):
    """Raised when an entity invariant is violated."""
    
    def __init__(self, message: str, entity_type: str = "", field: str = ""):
        self.entity_type = entity_type
        self.field = field
        super().__init__(message, code="INVARIANT_VIOLATION")


class IdentifierCollision(CanonicalError):
    """Raised when a duplicate identifier is detected."""
    
    def __init__(self, message: str, identifier: str = ""):
        self.identifier = identifier
        super().__init__(message, code="IDENTIFIER_COLLISION")


class SerializationError(CanonicalError):
    """Raised when serialization or deserialization fails."""
    
    def __init__(self, message: str, version: str = ""):
        self.version = version
        super().__init__(message, code="SERIALIZATION_ERROR")


class ValidationError(CanonicalError):
    """Raised when validation fails."""
    
    def __init__(self, message: str, errors: list = None):
        self.errors = errors or []
        super().__init__(message, code="VALIDATION_ERROR")
