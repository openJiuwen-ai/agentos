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
