"""Application exception types shared by services."""

class DomainError(Exception):
    """Base error raised by a domain service."""


class ResourceNotFound(DomainError):
    """Raised when a resource is missing or not owned by the caller."""


class ConflictError(DomainError):
    """Raised when a requested state transition conflicts with existing data."""
