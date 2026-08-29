"""Shared exceptions for the thirdparty-agent domain.

Zero framework dependencies — safe to import from package, models, service,
and router layers.
"""


class ThirdpartyAgentError(Exception):
    """Root of all thirdparty-agent exceptions.

    Subclasses are mapped to HTTP status codes in the API layer via
    isinstance checks, so detailed error types propagate through the
    service layer without wrapping.
    """


class PackageTooLargeError(ThirdpartyAgentError):
    def __init__(self, size: int, max_bytes: int) -> None:
        self.size = size
        self.max_bytes = max_bytes
        super().__init__(f"package too large: {size} bytes (max {max_bytes})")


class InvalidUploadError(ThirdpartyAgentError):
    """Generic upload rejected by the gate (name/extension)."""


class InsufficientDiskSpaceError(ThirdpartyAgentError):
    """Not enough disk space on the target filesystem."""


class PackageLockedError(ThirdpartyAgentError):
    """The content digest is currently locked."""


class AgentNotFoundError(ThirdpartyAgentError):
    def __init__(self, key: str) -> None:
        super().__init__(f"not found: {key}")


class CardHasInstancesError(ThirdpartyAgentError):
    """Cannot delete a card that still has instances."""


class DefaultVersionProtectedError(ThirdpartyAgentError):
    """Idle default versions are deletable; leftover siblings are promoted first."""


class AgentServiceError(ThirdpartyAgentError):
    """Generic service failure (e.g. registry error)."""
