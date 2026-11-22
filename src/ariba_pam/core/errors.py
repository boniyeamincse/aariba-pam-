"""Standard exceptions and error responses for Ariba PAM."""

from typing import Any, Optional
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """RFC-compliant error body."""

    code: str
    message: str
    request_id: Optional[str] = None
    details: Optional[Any] = None


class PAMException(Exception):
    """Base exception for all Ariba PAM errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        code: Optional[str] = None,
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class UnauthorizedException(PAMException):
    """401 Unauthorized: caller identity cannot be verified."""

    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenException(PAMException):
    """403 Forbidden: resource visible but caller lacks authorization."""

    status_code = 403
    code = "FORBIDDEN"


class NotFoundException(PAMException):
    """404 Not Found: resource missing or concealed by default-deny scope."""

    status_code = 404
    code = "NOT_FOUND"


class ConflictException(PAMException):
    """409 Conflict: invalid state or conflicting idempotency payload."""

    status_code = 409
    code = "CONFLICT"


class ValidationException(PAMException):
    """422 Validation Error: input data fails validation rules."""

    status_code = 422
    code = "VALIDATION_FAILED"


class ServiceUnavailableException(PAMException):
    """503 Service Unavailable: required dependency unavailable."""

    status_code = 503
    code = "SERVICE_UNAVAILABLE"
