"""Create a sample catalog for the isolated lab. Run after database migrations."""

from sqlalchemy import select

from ariba_pam.config import settings
from ariba_pam.db.models import Asset, GatewayZone, Role, RoleAssignment, TargetAccount, User
from ariba_pam.db.session import SessionLocal

demo_user_id = "usr_catalog_demo"


def seed_catalog() -> None:
    if settings.environment != "lab":
        raise SystemExit("The catalog fixture requires the lab environment.")

    with SessionLocal.begin() as db:
        if db.get(User, demo_user_id) is not None:
            return

        requester = db.scalar(select(Role).where(Role.name == "requester"))
        if requester is None:
            requester = Role(name="requester", description="Access requester")
            db.add(requester)

        demo = User(
            id=demo_user_id,
            idp_issuer=settings.idp_issuer,
            idp_subject="catalog-demo",
            email="catalog-demo@example.test",
            full_name="Catalog Demo",
        )
        empty = User(
            id="usr_catalog_empty",
            idp_issuer=settings.idp_issuer,
            idp_subject="catalog-empty",
            email="catalog-empty@example.test",
            full_name="Catalog Empty",
        )
        zone = GatewayZone(id="zon_catalog_demo", name="catalog-demo")
        db.add_all([demo, empty, zone])
        db.flush()

        visible = Asset(
            id="ast_catalog_demo",
            name="Build Runner",
            environment="lab",
            team="catalog-demo",
            zone_id=zone.id,
            host="build-runner.example.test",
        )
        restricted = Asset(
            id="ast_catalog_restricted",
            name="Restricted Runner",
            environment="lab",
            team="catalog-restricted",
            zone_id=zone.id,
            host="restricted-runner.example.test",
        )
        assignment = RoleAssignment(
            user_id=demo.id,
            role_id=requester.id,
            scope_type="asset",
            scope_value=visible.id,
        )
        db.add_all([visible, restricted, assignment])
        db.flush()
        db.add(
            TargetAccount(
                id="act_catalog_demo",
                asset_id=visible.id,
                username="build-maintainer",
                requires_ticket=True,
            )
        )


if __name__ == "__main__":
    seed_catalog()
    print("Catalog fixture ready for the local lab.")
