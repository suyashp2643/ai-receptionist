from app.models.enums import ReceptionistStatus, WidgetInstallationStatus
from app.models.receptionist import Receptionist
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.models.widget_installation import WidgetInstallation
from app.seed_data.public_demo_tenants import PUBLIC_DEMO_SPECS, seed_public_demo_tenants
from sqlalchemy import select
from sqlalchemy.orm import Session


def _clear_any_existing_demo_tenants(db_session: Session) -> None:
    """Local development may already have these fictional demo tenants
    committed (from actually running scripts/seed_public_demos.py against
    the shared dev database) — clear them first so each test exercises a
    real "created" path regardless of that pre-existing state. Runs inside
    the test's own rolled-back transaction, so it never actually deletes
    anything outside the test."""
    slugs = [spec.slug for spec in PUBLIC_DEMO_SPECS]
    for tenant in db_session.execute(select(Tenant).where(Tenant.slug.in_(slugs))).scalars().all():
        db_session.delete(tenant)
    db_session.flush()


class TestSeedPublicDemoTenants:
    def test_creates_three_tenants_each_with_an_active_installation(self, db_session: Session):
        _clear_any_existing_demo_tenants(db_session)
        result = seed_public_demo_tenants(db_session)

        assert sorted(result.created) == sorted(spec.tenant_name for spec in PUBLIC_DEMO_SPECS)
        assert result.skipped == []

        for spec in PUBLIC_DEMO_SPECS:
            tenant = db_session.execute(select(Tenant).where(Tenant.slug == spec.slug)).scalar_one()
            installation = db_session.execute(
                select(WidgetInstallation).where(WidgetInstallation.tenant_id == tenant.id)
            ).scalar_one()
            assert installation.public_id == spec.public_id
            assert installation.status == WidgetInstallationStatus.ACTIVE

            receptionist = db_session.execute(
                select(Receptionist).where(Receptionist.tenant_id == tenant.id)
            ).scalar_one()
            assert receptionist.status == ReceptionistStatus.ACTIVE
            assert receptionist.welcome_message == spec.welcome_message
            assert receptionist.suggested_questions == spec.suggested_questions

    def test_no_tenant_member_or_user_is_created(self, db_session: Session):
        """'If demo users are unnecessary, do not create them' — the public
        widget API never requires a dashboard login, so these tenants must
        have zero members."""
        _clear_any_existing_demo_tenants(db_session)
        seed_public_demo_tenants(db_session)

        for spec in PUBLIC_DEMO_SPECS:
            tenant = db_session.execute(select(Tenant).where(Tenant.slug == spec.slug)).scalar_one()
            members = db_session.execute(select(TenantMember).where(TenantMember.tenant_id == tenant.id)).all()
            assert members == []

    def test_rerunning_is_idempotent(self, db_session: Session):
        _clear_any_existing_demo_tenants(db_session)
        first = seed_public_demo_tenants(db_session)
        second = seed_public_demo_tenants(db_session)

        assert len(first.created) == 3
        assert second.created == []
        assert sorted(second.skipped) == sorted(spec.tenant_name for spec in PUBLIC_DEMO_SPECS)

        tenants = (
            db_session.execute(select(Tenant).where(Tenant.slug.in_([spec.slug for spec in PUBLIC_DEMO_SPECS])))
            .scalars()
            .all()
        )
        assert len(tenants) == 3  # never duplicated

    def test_each_demo_has_distinct_content(self, db_session: Session):
        _clear_any_existing_demo_tenants(db_session)
        seed_public_demo_tenants(db_session)

        welcome_messages = set()
        suggested = set()
        for spec in PUBLIC_DEMO_SPECS:
            tenant = db_session.execute(select(Tenant).where(Tenant.slug == spec.slug)).scalar_one()
            receptionist = db_session.execute(
                select(Receptionist).where(Receptionist.tenant_id == tenant.id)
            ).scalar_one()
            welcome_messages.add(receptionist.welcome_message)
            suggested.add(tuple(receptionist.suggested_questions))

        assert len(welcome_messages) == 3
        assert len(suggested) == 3
