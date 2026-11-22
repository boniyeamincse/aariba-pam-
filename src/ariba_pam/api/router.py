"""API router aggregation."""

from fastapi import APIRouter
from ariba_pam.api.v1.auth import router as auth_router
from ariba_pam.api.v1.assets import router as assets_router
from ariba_pam.api.v1.requests import router as requests_router
from ariba_pam.api.v1.approvals import router as approvals_router
from ariba_pam.api.v1.grants import router as grants_router
from ariba_pam.api.v1.sessions import router as sessions_router
from ariba_pam.api.v1.admin import router as admin_router
from ariba_pam.api.v1.audit import router as audit_router
from ariba_pam.api.v1.recordings import router as recordings_router
from ariba_pam.api.internal.gateway import router as gateway_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(assets_router)
api_v1_router.include_router(requests_router)
api_v1_router.include_router(approvals_router)
api_v1_router.include_router(grants_router)
api_v1_router.include_router(sessions_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(recordings_router)

internal_router = APIRouter()
internal_router.include_router(gateway_router)
