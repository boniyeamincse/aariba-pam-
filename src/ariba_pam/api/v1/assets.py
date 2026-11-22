"""Asset and target inventory endpoints with default-deny scoping."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from ariba_pam.db.session import get_db
from ariba_pam.db.models import User, Asset
from ariba_pam.services.auth import get_current_user
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.core.errors import NotFoundException
from ariba_pam.api.schemas import AssetResponse, TargetAccountResponse

router = APIRouter(tags=["Asset & Target Inventory"])


@router.get("/assets", response_model=List[AssetResponse])
def list_assets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List permitted assets and their active target accounts.
    Default deny: only assets matching the user's role assignments are returned.
    """
    stmt = (
        select(Asset)
        .options(joinedload(Asset.accounts))
        .where(Asset.is_active == True)  # noqa: E712
    )
    all_assets = list(db.scalars(stmt).unique().all())
    permitted = ScopeChecker.filter_assets_for_user(current_user, all_assets)

    response = []
    for asset in permitted:
        accounts = [
            TargetAccountResponse(
                id=acc.id,
                username=acc.username,
                is_active=acc.is_active,
                requires_ticket=acc.requires_ticket,
                max_duration_seconds=acc.max_duration_seconds,
            )
            for acc in asset.accounts
            if acc.is_active
        ]
        response.append(
            AssetResponse(
                id=asset.id,
                name=asset.name,
                environment=asset.environment,
                team=asset.team,
                zone_id=asset.zone_id,
                host=asset.host,
                port=asset.port,
                is_active=asset.is_active,
                accounts=accounts,
            )
        )
    return response


@router.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve single asset details if within caller's scope.
    Guessed or out-of-scope identifiers return 404 to conceal restricted assets.
    """
    stmt = (
        select(Asset)
        .options(joinedload(Asset.accounts))
        .where(Asset.id == asset_id, Asset.is_active == True)  # noqa: E712
    )
    asset = db.scalar(stmt)
    ScopeChecker.assert_asset_scope(current_user, asset)

    accounts = [
        TargetAccountResponse(
            id=acc.id,
            username=acc.username,
            is_active=acc.is_active,
            requires_ticket=acc.requires_ticket,
            max_duration_seconds=acc.max_duration_seconds,
        )
        for acc in asset.accounts
        if acc.is_active
    ]
    return AssetResponse(
        id=asset.id,
        name=asset.name,
        environment=asset.environment,
        team=asset.team,
        zone_id=asset.zone_id,
        host=asset.host,
        port=asset.port,
        is_active=asset.is_active,
        accounts=accounts,
    )
