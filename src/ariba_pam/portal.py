"""Same-origin UI for the isolated Ariba PAM lab."""

from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse

from ariba_pam.config import settings
from ariba_pam.core.errors import NotFoundException

router = APIRouter(include_in_schema=False)
files = Path(__file__).with_name("portal_assets")
resources = {
    "catalog.css": "text/css",
    "catalog.js": "application/javascript",
}
headers = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
}


def lab_file(name: str, media_type: str) -> FileResponse:
    if settings.environment != "lab":
        raise NotFoundException("Portal not found")
    return FileResponse(files / name, media_type=media_type, headers=headers)


@router.get("/portal")
def catalog() -> Response:
    return lab_file("catalog.html", "text/html")


@router.get("/portal/{name}")
def catalog_resource(name: str) -> Response:
    media_type = resources.get(name)
    if media_type is None:
        raise NotFoundException("Portal resource not found")
    return lab_file(name, media_type)
