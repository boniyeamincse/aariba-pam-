"""Ariba PAM Control Plane main application and entrypoint."""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session
from ariba_pam.config import settings
from ariba_pam.core.errors import PAMException
from ariba_pam.db.session import engine, create_all_tables, get_db
from ariba_pam.api.router import api_v1_router, internal_router
from ariba_pam.portal import router as portal_router
from ariba_pam.services.alerts import soc_alerts_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown events."""
    # Ensure database schema is initialized for lab environments
    create_all_tables()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Ariba PAM - Privileged Access Management Control Plane",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Ensure every request has a traceable request ID."""
    request_id = request.headers.get("X-Request-ID", f"req_{uuid.uuid4().hex[:12]}")
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(PAMException)
async def pam_exception_handler(request: Request, exc: PAMException):
    """Handle domain exceptions with consistent machine-readable error format."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request_id,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation failures with structured details."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Input validation failed",
            "request_id": request_id,
            "details": exc.errors(),
        },
    )


@app.get("/health", tags=["Health & Operability"])
def health_check():
    """Liveness probe confirming service process is up."""
    return {
        "status": "healthy",
        "service": "ariba-pam-control-plane",
        "version": "0.1.0",
        "environment": settings.environment,
    }


@app.get("/ready", tags=["Health & Operability"])
def readiness_check():
    """Readiness probe verifying operational database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "disconnected",
                "error": str(e),
            },
        )


@app.get("/health/components", tags=["Health & Operability"])
def component_health_check(db: Session = Depends(get_db)):
    """Deep component health probe for NFR-08 (99.95% availability & health probes)."""
    return soc_alerts_service.get_system_health(db)


# Mount routers
app.include_router(api_v1_router)
app.include_router(internal_router)
app.include_router(portal_router)
