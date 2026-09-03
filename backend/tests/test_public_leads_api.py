from app.core.rate_limit import get_rate_limiter
from app.models.public_lead import PublicLead
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _lead_count(db_session: Session) -> int:
    return db_session.execute(select(func.count()).select_from(PublicLead)).scalar_one()


def _latest_lead(db_session: Session) -> PublicLead:
    # Ordered by created_at rather than assuming the table starts empty —
    # this dev database is shared with live manual verification, which may
    # leave its own rows behind; a test must only ever assert on the row it
    # just created, never on "the only row in the table."
    return db_session.execute(select(PublicLead).order_by(PublicLead.created_at.desc())).scalars().first()


def _valid_payload(**overrides) -> dict:
    payload = {
        "full_name": "Priya Sharma",
        "work_email": "Priya@Example.com",
        "company": "Sunrise Clinics LLC",
        "website": "https://example.com",
        "country": "United Arab Emirates",
        "industry": "Healthcare",
        "company_size": "11-50",
        "estimated_monthly_volume": "201-500",
        "primary_use_case": "Qualify inbound clinic enquiries after hours",
        "message": "We'd like to see a live demo for our clinic group.",
        "contact_consent": True,
        "marketing_consent": False,
        "hp_field": "",
    }
    payload.update(overrides)
    return payload


class TestPublicLeadSubmission:
    def setup_method(self, _):
        get_rate_limiter().reset()

    def test_valid_submission_is_persisted_and_normalized(self, db_backed_client: TestClient, db_session: Session):
        count_before = _lead_count(db_session)
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload())

        assert response.status_code == 201
        assert response.json() == {"received": True}
        assert _lead_count(db_session) == count_before + 1

        lead = _latest_lead(db_session)
        assert lead.full_name == "Priya Sharma"
        assert lead.normalized_email == "priya@example.com"
        # EmailStr itself lowercases the domain part (not the local part) —
        # normalized_email above is our own additional full-lowercase pass.
        assert lead.work_email == "Priya@example.com"
        assert lead.contact_consent is True
        assert lead.marketing_consent is False
        assert lead.submitted_ip_hash is not None
        # Never the raw client IP.
        assert lead.submitted_ip_hash != "testclient"

    def test_marketing_consent_is_stored_separately_from_contact_consent(
        self, db_backed_client: TestClient, db_session: Session
    ):
        count_before = _lead_count(db_session)
        response = db_backed_client.post(
            "/api/v1/public/leads", json=_valid_payload(contact_consent=True, marketing_consent=True)
        )
        assert response.status_code == 201
        assert _lead_count(db_session) == count_before + 1
        lead = _latest_lead(db_session)
        assert lead.contact_consent is True
        assert lead.marketing_consent is True

    def test_contact_consent_is_required(self, db_backed_client: TestClient, db_session: Session):
        count_before = _lead_count(db_session)
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(contact_consent=False))
        assert response.status_code == 422
        assert _lead_count(db_session) == count_before

    def test_honeypot_field_silently_drops_the_submission(self, db_backed_client: TestClient, db_session: Session):
        count_before = _lead_count(db_session)
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(hp_field="I am a bot"))

        # Identical success response — a caller must never be able to tell
        # spam filtering exists.
        assert response.status_code == 201
        assert response.json() == {"received": True}
        assert _lead_count(db_session) == count_before

    def test_html_in_a_text_field_is_rejected(self, db_backed_client: TestClient):
        response = db_backed_client.post(
            "/api/v1/public/leads", json=_valid_payload(company="<script>alert(1)</script>")
        )
        assert response.status_code == 422

    def test_overlong_message_is_rejected(self, db_backed_client: TestClient):
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(message="x" * 5001))
        assert response.status_code == 422

    def test_invalid_email_is_rejected(self, db_backed_client: TestClient):
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(work_email="not-an-email"))
        assert response.status_code == 422

    def test_website_must_be_a_url(self, db_backed_client: TestClient):
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(website="example.com"))
        assert response.status_code == 422

    def test_website_is_optional(self, db_backed_client: TestClient, db_session: Session):
        payload = _valid_payload()
        del payload["website"]
        response = db_backed_client.post("/api/v1/public/leads", json=payload)
        assert response.status_code == 201
        lead = _latest_lead(db_session)
        assert lead.website is None

    def test_extra_fields_are_rejected(self, db_backed_client: TestClient):
        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(unexpected_field="x"))
        assert response.status_code == 422

    def test_no_public_read_endpoint_exists(self, db_backed_client: TestClient):
        # A lead must never be retrievable through any public route — the
        # only method registered on this path is POST (405, not a route
        # that happens to return an empty list), and no /list-style route
        # exists at all (404).
        get_response = db_backed_client.get("/api/v1/public/leads")
        list_response = db_backed_client.get("/api/v1/public/leads/list")
        assert get_response.status_code == 405
        assert list_response.status_code == 404


class TestPublicLeadRateLimit:
    def setup_method(self, _):
        get_rate_limiter().reset()

    def test_sixth_submission_within_the_window_is_rate_limited(self, db_backed_client: TestClient):
        for _ in range(5):
            response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload())
            assert response.status_code == 201

        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload())
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_a_honeypot_hit_still_counts_against_the_rate_limit(self, db_backed_client: TestClient):
        # Otherwise a bot could bypass the limiter entirely by always
        # tripping the honeypot.
        for _ in range(5):
            response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload(hp_field="bot"))
            assert response.status_code == 201

        response = db_backed_client.post("/api/v1/public/leads", json=_valid_payload())
        assert response.status_code == 429
