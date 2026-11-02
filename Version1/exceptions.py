"""Custom exceptions used across the PRS."""


class PRSError(Exception):
    """Base class for all PRS errors."""


class AuthenticationError(PRSError):
    """User is not logged in or credentials are wrong (NFR-02)."""


class PermissionDenied(PRSError):
    """User is logged in but not allowed to do this."""


class NotFoundError(PRSError):
    """Requested patient or note does not exist (FR-03)."""


class ValidationError(PRSError):
    """Input data is invalid."""


class AIUnavailableError(PRSError):
    """The AI service could not be reached or gave an unusable answer."""
