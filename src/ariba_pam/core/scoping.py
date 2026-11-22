"""Resource-scoped authorization and server-side default-deny policy."""

from typing import List, Optional, Set
from ariba_pam.db.models import User, Asset, RoleAssignment
from ariba_pam.core.errors import ForbiddenException, NotFoundException


class ScopeChecker:
    """Evaluates whether a user's role assignments permit access to a given asset or resource."""

    @staticmethod
    def is_asset_in_scope(user: User, asset: Asset, required_role: Optional[str] = None) -> bool:
        """
        Check if an asset falls within the user's assigned scopes.
        Default Deny: returns False if no assignment covers the asset.
        """
        if not user.is_active:
            return False

        for assignment in user.role_assignments:
            if required_role and assignment.role.name != required_role:
                continue

            # Scope type checking
            st = assignment.scope_type.lower()
            sv = assignment.scope_value

            if st == "global" and sv == "*":
                return True
            if st == "environment" and sv.lower() == asset.environment.lower():
                return True
            if st == "team" and sv.lower() == asset.team.lower():
                return True
            if st == "asset" and sv == asset.id:
                return True

        return False

    @staticmethod
    def filter_assets_for_user(user: User, assets: List[Asset], required_role: Optional[str] = None) -> List[Asset]:
        """Filter a list of assets to include only those within the user's permitted scopes."""
        if not user.is_active:
            return []
        return [a for a in assets if ScopeChecker.is_asset_in_scope(user, a, required_role)]

    @staticmethod
    def get_user_roles(user: User) -> Set[str]:
        """Collect all unique role names assigned to user."""
        return {assignment.role.name for assignment in user.role_assignments}

    @staticmethod
    def assert_asset_scope(user: User, asset: Optional[Asset], required_role: Optional[str] = None) -> None:
        """
        Assert that the asset exists and is within scope.
        Conceals non-permitted assets with 404 to avoid disclosure of restricted identifiers.
        """
        if asset is None:
            raise NotFoundException("Resource not found", code="ASSET_NOT_FOUND")

        if not ScopeChecker.is_asset_in_scope(user, asset, required_role):
            # Default deny with concealment
            raise NotFoundException("Resource not found", code="ASSET_NOT_FOUND")
