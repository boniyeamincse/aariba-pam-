"""Validation, publication and evaluation of reviewed asset policies."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ariba_pam.core.errors import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ServiceUnavailableException,
    ValidationException,
)
from ariba_pam.core.scoping import ScopeChecker
from ariba_pam.db.base import ensure_utc, utc_now
from ariba_pam.db.models import AccessPolicyVersion, AdminChangeProposal, Asset, RequestRevision, TargetAccount, User


class PolicyRules(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allowed_target_account_ids: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(min_length=1)
    max_duration_seconds: int = Field(gt=0, le=2_147_483_647)
    required_approvals: int = Field(ge=1, le=5)
    requires_ticket: bool = False

    @field_validator("allowed_target_account_ids")
    @classmethod
    def reject_duplicate_accounts(cls, accounts: list[str]) -> list[str]:
        if len(accounts) != len(set(accounts)):
            raise ValueError("Target accounts must be unique")
        return accounts


def scoped_policy_asset(
    db: Session, asset_id: str | None, user: User, roles: tuple[str, ...], *, lock: bool = False
) -> Asset:
    statement = select(Asset).where(Asset.id == asset_id)
    if lock:
        statement = statement.with_for_update()
    asset = db.scalar(statement)
    if asset is None or not any(ScopeChecker.is_asset_in_scope(user, asset, role) for role in roles):
        raise NotFoundException("Policy asset not found", code="ASSET_NOT_FOUND")
    return asset


def latest_policy(db: Session, asset_id: str) -> AccessPolicyVersion | None:
    return db.scalar(
        select(AccessPolicyVersion)
        .where(AccessPolicyVersion.asset_id == asset_id)
        .order_by(AccessPolicyVersion.version.desc())
        .limit(1)
    )


def validate_proposed_policy(db: Session, asset: Asset, payload: object) -> PolicyRules:
    try:
        rules = PolicyRules.model_validate(payload)
    except ValidationError as exc:
        details = [
            {"field": ".".join(map(str, error["loc"])), "message": error["msg"]}
            for error in exc.errors(include_input=False, include_context=False)
        ]
        raise ValidationException("Invalid access policy rules", code="INVALID_POLICY", details=details) from exc

    account_ids = set(db.scalars(
        select(TargetAccount.id).where(
            TargetAccount.asset_id == asset.id,
            TargetAccount.is_active.is_(True),
            TargetAccount.id.in_(rules.allowed_target_account_ids),
        )
    ))
    if account_ids != set(rules.allowed_target_account_ids):
        raise ValidationException("Policy accounts must be active on the selected asset", code="INVALID_POLICY_ACCOUNTS")
    return rules


def check_expected_version(db: Session, asset_id: str, expected_version: int) -> None:
    current = latest_policy(db, asset_id)
    if expected_version != (current.version if current else 0):
        raise ConflictException("The active policy version has changed", code="STALE_POLICY_VERSION")


def publish_policy(db: Session, asset: Asset, proposal: AdminChangeProposal) -> AccessPolicyVersion:
    check_expected_version(db, asset.id, proposal.expected_version)
    rules = validate_proposed_policy(db, asset, proposal.change_payload)
    version = AccessPolicyVersion(
        asset_id=asset.id,
        version=proposal.expected_version + 1,
        rules=rules.model_dump(),
        proposal_id=proposal.id,
    )
    db.add(version)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictException("The active policy version has changed", code="STALE_POLICY_VERSION") from exc
    return version


def authorize_request(
    db: Session,
    asset: Asset,
    account: TargetAccount,
    start_at: datetime,
    end_at: datetime,
    ticket_ref: str | None,
    *,
    expected_policy_id: str | None = None,
) -> tuple[AccessPolicyVersion, PolicyRules]:
    version = latest_policy(db, asset.id)
    if version is None:
        raise ForbiddenException("No reviewed policy authorizes the target", code="POLICY_REQUIRED")
    if expected_policy_id is not None and expected_policy_id != version.id:
        raise ConflictException("Submit a new request under the current policy", code="POLICY_CHANGED")
    try:
        rules = PolicyRules.model_validate(version.rules)
    except ValidationError as exc:
        raise ServiceUnavailableException("Active policy could not be evaluated", code="INVALID_ACTIVE_POLICY") from exc

    if not asset.is_active or not account.is_active or account.asset_id != asset.id:
        raise ForbiddenException("Target access is unavailable", code="POLICY_TARGET_UNAVAILABLE")
    if account.id not in rules.allowed_target_account_ids:
        raise ForbiddenException("The policy does not allow this target account", code="POLICY_ACCOUNT_DENIED")

    start_at, end_at = ensure_utc(start_at), ensure_utc(end_at)
    duration = (end_at - start_at).total_seconds()
    if duration <= 0 or end_at <= utc_now():
        raise ValidationException("The requested access window is invalid or expired", code="INVALID_TIME_WINDOW")
    if duration > min(rules.max_duration_seconds, account.max_duration_seconds):
        raise ValidationException("The requested access window is too long", code="POLICY_DURATION_EXCEEDED")
    if (rules.requires_ticket or account.requires_ticket) and not (ticket_ref and ticket_ref.strip()):
        raise ValidationException("A ticket reference is required", code="TICKET_REQUIRED")

    return version, rules


def authorize_revision(db: Session, revision: RequestRevision) -> None:
    # Serialize a new authorization against publication of a replacement policy.
    asset = db.scalar(
        select(Asset).where(Asset.id == revision.asset_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    account = db.get(TargetAccount, revision.target_account_id, populate_existing=True)
    if asset is None or account is None:
        raise ForbiddenException("Target access is unavailable", code="POLICY_TARGET_UNAVAILABLE")
    authorize_request(
        db,
        asset,
        account,
        revision.requested_start_at,
        revision.requested_end_at,
        revision.ticket_ref,
        expected_policy_id=revision.policy_version_id,
    )
