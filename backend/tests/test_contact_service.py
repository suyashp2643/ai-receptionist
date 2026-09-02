"""Dedup-safety regression coverage for app/services/contact_service.py —
see that module's docstring for the exact guarantees being locked in here."""

from app.models.enums import PreferredContactMethod
from app.services.contact_service import capture_contact
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner


def _capture(db_session, tenant_id, **overrides):
    kwargs = dict(
        tenant_id=tenant_id,
        conversation_id=None,
        name=None,
        email=None,
        phone=None,
        preferred_contact_method=None,
        marketing_consent=False,
    )
    kwargs.update(overrides)
    return capture_contact(db_session, **kwargs)


class TestDedupByEmailOrPhone:
    def test_second_submission_with_same_email_updates_the_same_row(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, name="Jane", email="jane@example.com")
        second = _capture(db_session, tenant.id, email="JANE@EXAMPLE.COM")
        assert second.id == first.id

    def test_second_submission_with_same_phone_updates_the_same_row(self, db_session: Session):
        """Both forms include the same country code, just formatted
        differently — normalize_phone only strips punctuation/spacing, it
        does not infer a missing country code (documented limitation), so a
        meaningful dedup test must keep the leading "+1" on both sides."""
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, name="Jane", phone="+1 (555) 123-4567")
        second = _capture(db_session, tenant.id, phone="+1-555-123-4567")
        assert second.id == first.id

    def test_no_match_creates_a_new_contact(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, email="a@example.com")
        second = _capture(db_session, tenant.id, email="b@example.com")
        assert second.id != first.id

    def test_dedup_is_scoped_to_one_tenant(self, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        first = _capture(db_session, tenant_a.id, name="Jane", email="jane@example.com")
        second = _capture(db_session, tenant_b.id, email="jane@example.com")
        assert second.id != first.id
        assert second.tenant_id == tenant_b.id
        assert first.tenant_id == tenant_a.id


class TestConflictingIdentityFieldsAreNeverOverwritten:
    def test_conflicting_name_is_not_overwritten(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        _capture(db_session, tenant.id, name="Real Jane", email="jane@example.com")
        updated = _capture(db_session, tenant.id, name="Impersonator", email="jane@example.com")
        assert updated.name == "Real Jane"

    def test_conflicting_email_on_a_phone_match_is_not_overwritten(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        _capture(db_session, tenant.id, phone="+15551234567", email="real@example.com")
        updated = _capture(db_session, tenant.id, phone="+15551234567", email="attacker@example.com")
        assert updated.normalized_email == "real@example.com"

    def test_conflicting_phone_on_an_email_match_is_not_overwritten(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        _capture(db_session, tenant.id, email="jane@example.com", phone="+15551234567")
        updated = _capture(db_session, tenant.id, email="jane@example.com", phone="+19995550000")
        assert updated.normalized_phone == "+15551234567"


class TestSafeEnrichmentOfEmptyFields:
    def test_a_later_submission_can_fill_in_a_previously_empty_phone(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, email="jane@example.com")
        assert first.normalized_phone is None
        updated = _capture(db_session, tenant.id, email="jane@example.com", phone="+15551234567")
        assert updated.normalized_phone == "+15551234567"

    def test_a_later_submission_can_fill_in_a_previously_empty_name(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, email="jane@example.com")
        assert first.name is None
        updated = _capture(db_session, tenant.id, email="jane@example.com", name="Jane")
        assert updated.name == "Jane"

    def test_preferred_contact_method_is_freely_updated_not_treated_as_identity(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        _capture(
            db_session, tenant.id, email="jane@example.com", preferred_contact_method=PreferredContactMethod.EMAIL
        )
        updated = _capture(
            db_session, tenant.id, email="jane@example.com", preferred_contact_method=PreferredContactMethod.PHONE
        )
        assert updated.preferred_contact_method == PreferredContactMethod.PHONE


class TestMarketingConsentPreservation:
    def test_consent_only_becomes_true_via_explicit_true(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        contact = _capture(db_session, tenant.id, email="jane@example.com", marketing_consent=False)
        assert contact.marketing_consent is False
        assert contact.consent_captured_at is None

    def test_explicit_true_is_recorded_with_a_timestamp(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        contact = _capture(db_session, tenant.id, email="jane@example.com", marketing_consent=True)
        assert contact.marketing_consent is True
        assert contact.consent_captured_at is not None

    def test_a_later_false_or_omitted_checkbox_does_not_erase_prior_explicit_consent(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, email="jane@example.com", marketing_consent=True)
        first_consent_time = first.consent_captured_at

        updated = _capture(db_session, tenant.id, email="jane@example.com", marketing_consent=False)

        assert updated.id == first.id
        assert updated.marketing_consent is True
        assert updated.consent_captured_at == first_consent_time

    def test_consent_timestamp_is_not_reset_by_a_second_explicit_true(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        first = _capture(db_session, tenant.id, email="jane@example.com", marketing_consent=True)
        updated = _capture(db_session, tenant.id, email="jane@example.com", marketing_consent=True)
        assert updated.consent_captured_at == first.consent_captured_at
