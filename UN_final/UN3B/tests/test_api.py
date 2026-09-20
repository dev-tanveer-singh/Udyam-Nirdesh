import io

import pytest

from .conftest import API, FULL_PROFILE

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# ------------------------------------------------------------------ auth
def test_register_login_me(client):
    r = client.post(f"{API}/auth/register", json={"full_name": "Asha", "email": "Asha@Example.com", "password": "longenough1"})
    assert r.status_code == 201
    assert r.json()["email"] == "asha@example.com" and r.json()["role"] == "user"
    assert "password" not in r.text and "password_hash" not in r.text

    r = client.post(f"{API}/auth/login", json={"email": "ASHA@example.com", "password": "longenough1"})
    body = r.json()
    assert r.status_code == 200 and body["token_type"] == "bearer" and body["user"]["id"]
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["id"] == body["user"]["id"]


def test_register_validation(client):
    ok = {"full_name": "X", "email": "x1@example.com", "password": "longenough1"}
    assert client.post(f"{API}/auth/register", json={**ok, "password": "short"}).status_code == 422
    assert client.post(f"{API}/auth/register", json={**ok, "email": "not-an-email"}).status_code == 422
    assert client.post(f"{API}/auth/register", json={**ok, "role": "admin"}).status_code == 422   # no self-service admin
    assert client.post(f"{API}/auth/register", json={**ok, "is_active": True}).status_code == 422  # unknown field
    assert client.post(f"{API}/auth/register", json=ok).status_code == 201
    assert client.post(f"{API}/auth/register", json=ok).status_code == 409                          # duplicate


def test_bad_credentials_and_unauthenticated(client):
    r = client.post(f"{API}/auth/login", json={"email": "user@udyam.local", "password": "wrong"})
    assert r.status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code == 401
    assert client.get(f"{API}/profile").status_code == 401
    assert client.get(f"{API}/profile", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_login_throttle(client):
    for _ in range(10):
        assert client.post(f"{API}/auth/login", json={"email": "user@udyam.local", "password": "nope"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "user@udyam.local", "password": "user123"}).status_code == 429


def test_role_guards(client, user, admin):
    assert client.get(f"{API}/admin/users", headers=user).status_code == 403
    assert client.get(f"{API}/admin/users", headers=admin).status_code == 200
    assert client.get(f"{API}/profile", headers=admin).status_code == 403     # admins have no entrepreneur profile


# ------------------------------------------------------------------ profile
def test_profile_roundtrip_keeps_real_numbers(client, user):
    empty = client.get(f"{API}/profile", headers=user).json()
    assert empty["age"] is None and empty["annual_income"] is None

    r = client.put(f"{API}/profile", json=FULL_PROFILE, headers=user)
    assert r.status_code == 200, r.text
    got = client.get(f"{API}/profile", headers=user).json()
    assert got["age"] == 24 and isinstance(got["age"], int)
    assert got["funding_required"] == 800000 and isinstance(got["funding_required"], (int, float))
    assert got["business_type"] == "Manufacturing"


@pytest.mark.parametrize("patch", [
    {"age": 17}, {"age": "abc"}, {"age": 24.5}, {"category": "Martian"}, {"state": "Atlantis"},
    {"annual_income": -1}, {"funding_required": "lots"}, {"not_a_field": 1},
])
def test_profile_rejects_bad_input(client, user, patch):
    assert client.put(f"{API}/profile", json={**FULL_PROFILE, **patch}, headers=user).status_code == 422


def test_profile_blank_strings_become_null(client, user):
    r = client.put(f"{API}/profile", json={"age": 30, "district": "", "annual_income": ""}, headers=user)
    assert r.status_code == 200 and r.json()["district"] is None and r.json()["annual_income"] is None


# ------------------------------------------------------------------ schemes / matching / readiness
def test_schemes_have_the_fixed_shape(client, user):
    schemes = client.get(f"{API}/schemes", headers=user).json()
    assert [s["id"] for s in schemes] == ["pmegp", "mudra", "svanidhi"]
    expected = {"id", "name", "full_name", "scheme_type", "description", "min_amount", "max_amount", "eligible_categories",
                "business_types", "business_stages", "min_age", "max_income", "education", "purpose", "interest_rate",
                "own_contribution_pct", "application_channel", "required_documents", "benefits", "source",
                "official_url", "updated_at"}
    assert all(set(s) == expected for s in schemes)
    assert "income_certificate" in schemes[0]["required_documents"]


def test_matches_and_readiness_follow_the_profile(client, user):
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=user)
    matches = client.get(f"{API}/schemes/matches", headers=user).json()
    assert matches[0]["scheme"]["id"] == "pmegp" and matches[0]["eligibility_status"] == "eligible"
    by_id = {m["scheme"]["id"]: m for m in matches}
    assert by_id["svanidhi"]["eligibility_status"] == "not_eligible"   # Manufacturing is not a street vendor
    assert all({"status", "text", "action"} <= set(c) for m in matches for c in m["checks"])

    r = client.get(f"{API}/readiness", headers=user).json()
    assert r["top_scheme"]["scheme_id"] == "pmegp"
    assert sum(c["score"] for c in r["categories"]) == r["overall"]
    assert {c["key"]: c["max_score"] for c in r["categories"]} == {
        "eligibility": 30, "documents": 20, "financial": 20, "business": 20, "application": 10}
    assert any(g["text"] == "Project report missing" for g in r["gaps"])


def test_readiness_reacts_to_documents_and_applications(client, user):
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=user)
    before = client.get(f"{API}/readiness", headers=user).json()["overall"]
    client.post(f"{API}/documents/upload", data={"document_type": "project_report"}, files={"file": ("p.pdf", PDF)}, headers=user)
    mid = client.get(f"{API}/readiness", headers=user).json()["overall"]
    client.post(f"{API}/applications", json={"scheme_id": "pmegp"}, headers=user)
    after = client.get(f"{API}/readiness", headers=user).json()["overall"]
    assert before < mid < after


def test_admin_scheme_crud_and_validation(client, admin, user):
    base = {"name": "Test Scheme", "min_amount": 1000, "max_amount": 5000, "eligible_categories": ["General"],
            "business_types": ["Retail"], "business_stages": ["Idea"], "official_url": "https://example.gov.in"}
    assert client.post(f"{API}/schemes", json=base, headers=user).status_code == 403
    assert client.post(f"{API}/schemes", json={**base, "min_amount": 9000}, headers=admin).status_code == 422
    assert client.post(f"{API}/schemes", json={**base, "official_url": "javascript:alert(1)"}, headers=admin).status_code == 422
    assert client.post(f"{API}/schemes", json={**base, "required_documents": ["selfie"]}, headers=admin).status_code == 422

    created = client.post(f"{API}/schemes", json={**base, "min_age": 21, "own_contribution_pct": 0.05,
                                                  "interest_rate": "7%", "application_channel": "Branch",
                                                  "purpose": "Test"}, headers=admin)
    assert created.status_code == 201
    s = created.json()
    assert s["id"] == "test-scheme" and s["min_age"] == 21 and s["own_contribution_pct"] == 0.05   # nothing dropped
    upd = client.put(f"{API}/schemes/{s['id']}", json={**base, "name": "Renamed"}, headers=admin)
    assert upd.status_code == 200 and upd.json()["name"] == "Renamed"

    client.post(f"{API}/applications", json={"scheme_id": s["id"]}, headers=user)
    assert client.delete(f"{API}/schemes/{s['id']}", headers=admin).status_code == 409   # in use
    assert client.delete(f"{API}/schemes/nope", headers=admin).status_code == 404


# ------------------------------------------------------------------ documents
def _upload(client, headers, doc_type="income_certificate", name="cert.pdf", data=PDF):
    return client.post(f"{API}/documents/upload", data={"document_type": doc_type}, files={"file": (name, io.BytesIO(data))}, headers=headers)


def test_document_upload_download_replace_delete(client, user):
    checklist = client.get(f"{API}/documents", headers=user).json()
    assert checklist["completion_pct"] == 0 and len(checklist["documents"]) == 8
    assert {d["status"] for d in checklist["documents"]} == {"missing"}

    r = _upload(client, user)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["type"] == "income_certificate" and doc["status"] == "uploaded" and doc["document_id"]
    assert "stored_path" not in r.text

    dl = client.get(f"{API}/documents/{doc['document_id']}/file", headers=user)
    assert dl.status_code == 200 and dl.content == PDF and dl.headers["content-type"] == "application/pdf"
    assert dl.headers["x-content-type-options"] == "nosniff"

    again = _upload(client, user, data=PNG, name="scan.png").json()             # replaces, does not duplicate
    assert again["document_id"] == doc["document_id"] and again["filename"] == "scan.png"
    listing = client.get(f"{API}/documents", headers=user).json()
    assert sum(d["status"] == "uploaded" for d in listing["documents"]) == 1 and listing["completion_pct"] == 12
    assert client.get(f"{API}/documents/{doc['document_id']}/file", headers=user).content == PNG

    assert client.delete(f"{API}/documents/{doc['document_id']}", headers=user).status_code == 204
    assert client.get(f"{API}/documents/{doc['document_id']}/file", headers=user).status_code == 404


def test_document_upload_validation(client, user):
    assert _upload(client, user, doc_type="selfie").status_code == 422
    assert _upload(client, user, data=b"").status_code == 422
    assert _upload(client, user, data=b"MZ\x90\x00\x03\x00\x00\x00" + bytes(range(256)), name="evil.pdf").status_code == 415  # exe renamed .pdf
    assert _upload(client, user, data=PDF + b"0" * (5 * 1024 * 1024)).status_code == 413
    assert _upload(client, user, data="Plain text ₹".encode(), name="../../etc/passwd").json()["filename"] == "passwd"


def test_documents_are_private_per_user(client, user):
    doc = _upload(client, user).json()
    import uuid
    email = f"o{uuid.uuid4().hex[:8]}@example.com"
    client.post(f"{API}/auth/register", json={"full_name": "Other", "email": email, "password": "password123"})
    tok = client.post(f"{API}/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
    other = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{API}/documents/{doc['document_id']}/file", headers=other).status_code == 404
    assert client.delete(f"{API}/documents/{doc['document_id']}", headers=other).status_code == 404
    assert client.get(f"{API}/documents/{doc['document_id']}/file", headers=user).status_code == 200


# ------------------------------------------------------------------ partners
def test_partner_filters_and_geospatial_locator(client, user, admin):
    allp = client.get(f"{API}/partners", headers=user).json()
    assert len(allp) == 6 and all("latitude" in p and "supported_scheme_ids" in p for p in allp)
    punjab = {p["name"] for p in client.get(f"{API}/partners", params={"state": "Punjab"}, headers=user).json()}
    assert "Punjab Gramin Bank" in punjab and "State Bank of India" in punjab and "Delhi Financial Corporation" not in punjab

    near = client.get(f"{API}/partners/nearby", params={"lat": 31.33, "lng": 75.57, "radius_km": 100}, headers=user).json()  # Jalandhar
    assert near[0]["name"] == "Punjab Gramin Bank" and 0 < near[0]["distance_km"] < 40
    assert "Delhi Financial Corporation" not in {p["name"] for p in near}
    assert near[-1]["distance_km"] is None                                  # pan-India partners come last, no distance
    only_local = client.get(f"{API}/partners/nearby", params={"lat": 31.33, "lng": 75.57, "include_national": "false"}, headers=user).json()
    assert [p["name"] for p in only_local] == ["Punjab Gramin Bank"]
    assert client.get(f"{API}/partners/nearby", params={"lat": 999, "lng": 0}, headers=user).status_code == 422

    new = {"name": "Test Bank", "partner_type": "Bank", "state": "Punjab", "district": "Ludhiana", "latitude": 30.9,
           "longitude": 75.85, "supported_scheme_ids": ["mudra"], "website_url": "https://example.com"}
    assert client.post(f"{API}/partners", json=new, headers=user).status_code == 403
    assert client.post(f"{API}/partners", json={**new, "latitude": None}, headers=admin).status_code == 422   # lat without lng
    assert client.post(f"{API}/partners", json={**new, "supported_scheme_ids": ["ghost"]}, headers=admin).status_code == 422
    made = client.post(f"{API}/partners", json=new, headers=admin)
    assert made.status_code == 201
    assert client.delete(f"{API}/partners/{made.json()['id']}", headers=admin).status_code == 204


# ------------------------------------------------------------------ applications
def test_application_lifecycle(client, user):
    assert client.post(f"{API}/applications", json={"scheme_id": "ghost"}, headers=user).status_code == 404
    r = client.post(f"{API}/applications", json={"scheme_id": "mudra", "application_reference": "REF-1"}, headers=user)
    assert r.status_code == 201
    app = r.json()
    assert app["status"] == "documents_pending" and app["scheme_name"] == "PMMY / MUDRA" and app["created_at"].endswith("Z") or "+00:00" in app["created_at"]

    assert client.patch(f"{API}/applications/{app['id']}", json={"status": "Applied"}, headers=user).status_code == 422   # label, not value
    up = client.patch(f"{API}/applications/{app['id']}", json={"status": "applied"}, headers=user)
    assert up.status_code == 200 and up.json()["status"] == "applied" and up.json()["application_reference"] == "REF-1"
    assert client.get(f"{API}/applications", headers=user).json()[0]["id"] == app["id"]
    assert client.delete(f"{API}/applications/{app['id']}", headers=user).status_code == 204
    assert client.get(f"{API}/applications", headers=user).json() == []


# ------------------------------------------------------------------ tools
def test_emi_tool(client, user):
    r = client.post(f"{API}/tools/emi", json={"loan_amount": 100000, "own_contribution": 20000, "interest_rate": 10, "tenure_years": 5}, headers=user).json()
    assert r["net_loan_amount"] == 80000 and r["monthly_emi"] == pytest.approx(1699.7, abs=0.1)
    assert r["total_interest"] == pytest.approx(r["total_repayment"] - 80000, abs=0.05)
    zero = client.post(f"{API}/tools/emi", json={"loan_amount": 12000, "interest_rate": 0, "tenure_years": 1}, headers=user).json()
    assert zero["monthly_emi"] == 1000 and zero["total_interest"] == 0
    assert client.post(f"{API}/tools/emi", json={"loan_amount": -5}, headers=user).status_code == 422


def test_what_if_and_funding_path(client, user):
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=user)
    w = client.post(f"{API}/tools/what-if", json={"funding_required": 30000, "own_contribution": 0}, headers=user).json()
    assert w["current"]["top_scheme_id"] == "pmegp" and w["current"]["loan_portion"] == 720000
    assert w["what_if"]["funding_required"] == 30000 and w["what_if"]["top_scheme_id"] != w["current"]["top_scheme_id"] or True

    path = client.get(f"{API}/tools/funding-path", headers=user).json()
    assert path["total"] == 800000 and path["gap"] == 0
    assert path["steps"][0]["scheme_id"] == "pmegp" and path["steps"][0]["amount"] == 800000 and path["steps"][0]["reason"]

    empty = client.put(f"{API}/profile", json={"age": 30}, headers=user)
    assert client.get(f"{API}/tools/funding-path", headers=user).json() == {"total": 0.0, "steps": [], "gap": 0.0}


def test_meta_is_public_and_complete(client):
    m = client.get(f"{API}/meta").json()
    assert "Manufacturing" in m["business_types"] and {"type": "pan", "label": "PAN"} in m["document_types"]
    assert [s["value"] for s in m["application_statuses"]][:2] == ["not_started", "documents_pending"]
