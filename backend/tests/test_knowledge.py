import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.services.knowledge_service import CHUNK_OVERLAP, CHUNK_SIZE, chunk_text
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def test_chunking_is_deterministic():
    text = "Sentence one. " * 300  # long enough to require multiple chunks
    assert chunk_text(text) == chunk_text(text)


def test_chunking_respects_size_and_overlap():
    text = "a" * (CHUNK_SIZE * 3)
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert len(chunk) == CHUNK_SIZE
    # Consecutive chunks overlap by CHUNK_OVERLAP characters.
    assert chunks[0][-CHUNK_OVERLAP:] == chunks[1][:CHUNK_OVERLAP]


def test_empty_text_produces_no_chunks():
    assert chunk_text("   ") == []


def test_create_manual_source_and_document(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    source = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/sources",
        json={"type": "manual", "title": "About Us"},
        headers=headers,
    ).json()

    document_response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/documents",
        json={"source_id": source["id"], "title": "About Us", "raw_text": "We are open every day from 9 to 5."},
        headers=headers,
    )
    assert document_response.status_code == 201


def test_website_source_type_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/sources",
        json={"type": "website", "title": "My Website"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_knowledge_text_size_limit_enforced(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)
    source = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/sources", json={"type": "manual", "title": "Src"}, headers=headers
    ).json()

    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/documents",
        json={"source_id": source["id"], "title": "Too Big", "raw_text": "x" * 200_001},
        headers=headers,
    )
    assert response.status_code == 422


def test_search_finds_relevant_chunk_and_stays_tenant_scoped(db_backed_client: TestClient, db_session: Session):
    tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
    tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

    source_a = db_backed_client.post(
        f"/api/v1/tenants/{tenant_a.id}/knowledge/sources",
        json={"type": "manual", "title": "Src"},
        headers=_auth_headers(owner_a),
    ).json()
    db_backed_client.post(
        f"/api/v1/tenants/{tenant_a.id}/knowledge/documents",
        json={
            "source_id": source_a["id"],
            "title": "Parking",
            "raw_text": "Free parking is available behind the building for all visitors.",
        },
        headers=_auth_headers(owner_a),
    )

    source_b = db_backed_client.post(
        f"/api/v1/tenants/{tenant_b.id}/knowledge/sources",
        json={"type": "manual", "title": "Src"},
        headers=_auth_headers(owner_b),
    ).json()
    db_backed_client.post(
        f"/api/v1/tenants/{tenant_b.id}/knowledge/documents",
        json={
            "source_id": source_b["id"],
            "title": "Parking B",
            "raw_text": "Tenant B also has free parking information that must never leak to Tenant A.",
        },
        headers=_auth_headers(owner_b),
    )

    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant_a.id}/knowledge/search",
        json={"query": "parking"},
        headers=_auth_headers(owner_a),
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) >= 1
    assert all("Tenant B" not in r["content"] for r in results)


def test_delete_document_removes_its_chunks(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)
    source = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/sources", json={"type": "manual", "title": "Src"}, headers=headers
    ).json()
    document = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/documents",
        json={"source_id": source["id"], "title": "Doc", "raw_text": "Some searchable unique content xyzzyplugh."},
        headers=headers,
    ).json()

    db_backed_client.delete(f"/api/v1/tenants/{tenant.id}/knowledge/documents/{document['id']}", headers=headers)

    search_response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/knowledge/search", json={"query": "xyzzyplugh"}, headers=headers
    )
    assert search_response.json()["results"] == []
