import io

from .conftest import API, FULL_PROFILE

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(client, h, doc_type, data=PDF, name="a.pdf"):
    return client.post(f"{API}/documents/upload", data={"document_type": doc_type}, files={"file": (name, io.BytesIO(data))}, headers=h)


# ------------------------------------------------------------------ schemes
def test_scheme_fixed_shape(client, user_h):
    s = client.get(f"{API}/schemes", headers=user_h).json()
    assert [x["id"] for x in s] == ["pmegp", "mudra", "svanidhi"]
    keys = set(s[0])
    assert {"min_amount", "max_amount", "eligible_categories", "business_types", "business_stages", "min_age",
            "own_contribution_pct", "required_documents", "application_channel", "official_url"} <= keys
    assert "ageMin" not in keys and "cats" not in keys
    assert s[0]["required_documents"][0] == "identity_proof"


def test_matches_rank_and_explain(client, user_h):
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=user_h)
    m = client.get(f"{API}/schemes/matches", headers=user_h).json()
    assert m[0]["scheme"]["id"] == "pmegp" and m[0]["eligibility_status"] == "eligible" and m[0]["match_pct"] == 100
    assert m[-1]["scheme"]["id"] == "svanidhi" and m[-1]["eligibility_status"] == "not_eligible"
    assert {c["status"] for c in m[-1]["checks"]} <= {"ok", "warn", "bad"}


def test_scheme_admin_crud_and_validation(client, admin_h, user_h):
    body = {"name": "Test Scheme!", "min_amount": 1000, "max_amount": 50000, "eligible_categories": ["General"],
            "business_types": ["Retail"], "business_stages": ["Idea"], "official_url": "https://example.gov.in/"}
    assert client.post(f"{API}/schemes", json=body, headers=user_h).status_code == 403
    assert client.post(f"{API}/schemes", json={**body, "min_amount": 9e9}, headers=admin_h).status_code == 422
    assert client.post(f"{API}/schemes", json={**body, "official_url": "javascript:alert(1)"}, headers=admin_h).status_code == 422
    assert client.post(f"{API}/schemes", json={**body, "required_documents": ["nope"]}, headers=admin_h).status_code == 422
    created = client.post(f"{API}/schemes", json=body, headers=admin_h)
    assert created.status_code == 201
    sid = created.json()["id"]
    assert sid == "test-scheme" and created.json()["min_age"] == 18 and created.json()["own_contribution_pct"] == 0.1
    upd = client.put(f"{API}/schemes/{sid}", json={**body, "min_age": 21, "own_contribution_pct": 0.25}, headers=admin_h)
    assert upd.json()["min_age"] == 21 and upd.json()["own_contribution_pct"] == 0.25   # fields no longer dropped on edit
    assert client.delete(f"{API}/schemes/{sid}", headers=admin_h).status_code == 204
    assert client.get(f"{API}/schemes/{sid}", headers=user_h).status_code == 404


def test_cannot_delete_scheme_with_applications(client, admin_h, user_h):
    client.post(f"{API}/applications", json={"scheme_id": "svanidhi"}, headers=user_h)
    assert client.delete(f"{API}/schemes/svanidhi", headers=admin_h).status_code == 409


# ------------------------------------------------------------------ documents
def test_document_checklist_and_lifecycle(client, user_h):
    lst = client.get(f"{API}/documents", headers=user_h).json()
    assert len(lst["documents"]) == 8 and lst["completion_pct"] == 0
    assert lst["documents"][0] == {"type": "identity_proof", "label": "Identity Proof", "status": "missing",
                                   "document_id": None, "filename": None, "size_bytes": None, "uploaded_at": None}
    r = upload(client, user_h, "income_certificate")
    assert r.status_code == 201 and r.json()["status"] == "uploaded"
    doc_id = r.json()["document_id"]
    assert client.get(f"{API}/documents", headers=user_h).json()["completion_pct"] == 12   # 1 of 8
    dl = client.get(f"{API}/documents/{doc_id}/file", headers=user_h)
    assert dl.status_code == 200 and dl.content == PDF and dl.headers["content-type"] == "application/pdf"
    assert dl.headers["x-content-type-options"] == "nosniff"
    # re-upload replaces (still exactly one document of that type)
    r2 = upload(client, user_h, "income_certificate", PNG, "scan.png")
    assert r2.status_code == 201 and r2.json()["document_id"] == doc_id
    assert client.get(f"{API}/documents/{doc_id}/file", headers=user_h).headers["content-type"] == "image/png"
    assert client.delete(f"{API}/documents/{doc_id}", headers=user_h).status_code == 204
    assert client.get(f"{API}/documents/{doc_id}/file", headers=user_h).status_code == 404


def test_document_upload_rejections(client, user_h):
    assert upload(client, user_h, "not_a_type").status_code == 422
    assert upload(client, user_h, "pan", b"").status_code == 422
    assert upload(client, user_h, "pan", b"MZ\x90\x00\x03\x00\x00\x00", "virus.pdf").status_code == 415   # exe renamed .pdf
    assert upload(client, user_h, "pan", b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert upload(client, user_h, "pan", b"plain text is fine", "n.txt").status_code == 201


def test_documents_are_private(client):
    from .conftest import auth_headers, make_user
    a = auth_headers(client, *make_user(client))
    b = auth_headers(client, *make_user(client))
    doc_id = upload(client, a, "pan").json()["document_id"]
    assert client.get(f"{API}/documents/{doc_id}/file", headers=b).status_code == 404
    assert client.delete(f"{API}/documents/{doc_id}", headers=b).status_code == 404
    assert client.get(f"{API}/documents/{doc_id}/file").status_code == 401


def test_filename_cannot_escape(client, user_h):
    r = upload(client, user_h, "pan", PDF, "../../etc/passwd")
    assert r.status_code == 201 and r.json()["filename"] == "passwd"


# ------------------------------------------------------------------ partners
def test_partners_filters_and_locator(client, user_h):
    allp = client.get(f"{API}/partners", headers=user_h).json()
    assert len(allp) == 6 and {"state", "district", "latitude", "longitude", "supported_scheme_ids"} <= set(allp[0])
    punjab = client.get(f"{API}/partners", params={"state": "Punjab"}, headers=user_h).json()
    assert "Punjab Gramin Bank" in [p["name"] for p in punjab] and "Delhi Financial Corporation" not in [p["name"] for p in punjab]
    assert "State Bank of India" in [p["name"] for p in punjab]              # pan-India partners always included
    # near Ludhiana -> Punjab Gramin Bank (Kapurthala, ~50 km); Delhi is ~300 km away
    near = client.get(f"{API}/partners/nearby", params={"lat": 30.9, "lng": 75.85, "radius_km": 100}, headers=user_h).json()
    assert near[0]["name"] == "Punjab Gramin Bank" and 30 < near[0]["distance_km"] < 80
    assert all(p["name"] != "Delhi Financial Corporation" for p in near)
    assert near[-1]["distance_km"] is None                                   # pan-India partners come last
    only = client.get(f"{API}/partners/nearby", params={"lat": 30.9, "lng": 75.85, "include_national": "false"}, headers=user_h).json()
    assert [p["name"] for p in only] == ["Punjab Gramin Bank"]
    assert client.get(f"{API}/partners/nearby", params={"lat": 999, "lng": 0}, headers=user_h).status_code == 422
    by_scheme = client.get(f"{API}/partners", params={"scheme_id": "pmegp"}, headers=user_h).json()
    assert all("pmegp" in p["supported_scheme_ids"] for p in by_scheme)


def test_partner_admin(client, admin_h, user_h):
    body = {"name": "Test Bank", "partner_type": "Bank", "state": "All States", "website_url": "https://example.com", "supported_scheme_ids": ["mudra"]}
    assert client.post(f"{API}/partners", json=body, headers=user_h).status_code == 403
    assert client.post(f"{API}/partners", json={**body, "supported_scheme_ids": ["ghost"]}, headers=admin_h).status_code == 422
    assert client.post(f"{API}/partners", json={**body, "latitude": 10}, headers=admin_h).status_code == 422   # lat without lng
    r = client.post(f"{API}/partners", json=body, headers=admin_h)
    assert r.status_code == 201 and r.json()["state"] is None                # "All States" is stored as null
    assert client.delete(f"{API}/partners/{r.json()['id']}", headers=admin_h).status_code == 204


# ------------------------------------------------------------------ applications
def test_application_lifecycle(client, user_h):
    assert client.post(f"{API}/applications", json={"scheme_id": "ghost"}, headers=user_h).status_code == 404
    r = client.post(f"{API}/applications", json={"scheme_id": "pmegp", "application_reference": " REF-1 "}, headers=user_h)
    assert r.status_code == 201
    a = r.json()
    assert a["status"] == "documents_pending" and a["scheme_name"] == "PMEGP" and a["application_reference"] == "REF-1"
    assert a["created_at"].endswith("Z") or "+00:00" in a["created_at"]
    bad = client.patch(f"{API}/applications/{a['id']}", json={"status": "Applied"}, headers=user_h)   # display text is not a valid value
    assert bad.status_code == 422
    ok = client.patch(f"{API}/applications/{a['id']}", json={"status": "applied"}, headers=user_h)
    assert ok.json()["status"] == "applied" and ok.json()["application_reference"] == "REF-1"
    assert len(client.get(f"{API}/applications", headers=user_h).json()) == 1
    assert client.delete(f"{API}/applications/{a['id']}", headers=user_h).status_code == 204
    assert client.get(f"{API}/applications", headers=user_h).json() == []


def test_applications_are_private(client):
    from .conftest import auth_headers, make_user
    a = auth_headers(client, *make_user(client))
    b = auth_headers(client, *make_user(client))
    app_id = client.post(f"{API}/applications", json={"scheme_id": "mudra"}, headers=a).json()["id"]
    assert client.patch(f"{API}/applications/{app_id}", json={"status": "approved"}, headers=b).status_code == 404
    assert client.delete(f"{API}/applications/{app_id}", headers=b).status_code == 404


# ------------------------------------------------------------------ readiness + tools
def test_readiness_moves_with_profile_docs_and_application(client, user_h):
    base = client.get(f"{API}/readiness", headers=user_h).json()
    assert base["overall"] == 5 and base["top_scheme"]["scheme_id"] == "pmegp"
    assert sum(c["max_score"] for c in base["categories"]) == 100
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=user_h)
    after_profile = client.get(f"{API}/readiness", headers=user_h).json()["overall"]
    assert after_profile > base["overall"]
    upload(client, user_h, "project_report")
    after_doc = client.get(f"{API}/readiness", headers=user_h).json()["overall"]
    assert after_doc > after_profile
    client.post(f"{API}/applications", json={"scheme_id": "pmegp"}, headers=user_h)
    full = client.get(f"{API}/readiness", headers=user_h).json()
    assert full["overall"] > after_doc and any(i["category"] for i in full["strengths"])
    assert all(i["status"] != "ok" for i in full["gaps"])


def test_emi_calculator(client, user_h):
    r = client.post(f"{API}/tools/emi", json={"loan_amount": 100000, "own_contribution": 20000, "interest_rate": 10, "tenure_years": 5}, headers=user_h)
    assert r.status_code == 200
    b = r.json()
    assert b["net_loan_amount"] == 80000 and abs(b["monthly_emi"] - 1699.75) < 0.05
    assert abs(b["total_repayment"] - 60 * b["monthly_emi"]) < 1
    zero = client.post(f"{API}/tools/emi", json={"loan_amount": 120000, "interest_rate": 0, "tenure_years": 1}, headers=user_h).json()
    assert zero["monthly_emi"] == 10000 and zero["total_interest"] == 0
    mor = client.post(f"{API}/tools/emi", json={"loan_amount": 100000, "interest_rate": 12, "tenure_years": 2, "moratorium_months": 6}, headers=user_h).json()
    plain = client.post(f"{API}/tools/emi", json={"loan_amount": 100000, "interest_rate": 12, "tenure_years": 2}, headers=user_h).json()
    assert mor["monthly_emi"] > plain["monthly_emi"]                         # interest capitalised during moratorium
    assert client.post(f"{API}/tools/emi", json={"loan_amount": -5}, headers=user_h).status_code == 422


def test_what_if_and_funding_path(client, user_h):
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=user_h)
    w = client.post(f"{API}/tools/what-if", json={"funding_required": 20000, "own_contribution": 2000}, headers=user_h).json()
    assert w["current"]["top_scheme_id"] == "pmegp" and w["current"]["funding_required"] == 800000
    assert w["what_if"]["loan_portion"] == 18000 and w["what_if"]["top_scheme_id"] != "pmegp"   # 20k is below PMEGP's minimum
    p = client.get(f"{API}/tools/funding-path", headers=user_h).json()
    assert p["steps"][0] == {"source": "scheme", "scheme_id": "pmegp", "scheme_name": "PMEGP", "eligibility_status": "eligible",
                             "amount": 800000, "reason": "Highest-ranked eligible scheme with a \u20b950,00,000 limit"}
    assert p["gap"] == 0 and p["total"] == 800000
    empty = client.get(f"{API}/tools/funding-path", headers=client.post(f"{API}/auth/login", json={"email": "user@udyam.local", "password": "user123"}).json() and {"Authorization": "Bearer " + client.post(f"{API}/auth/login", json={"email": "user@udyam.local", "password": "user123"}).json()["access_token"]}).json()
    assert empty["steps"] == [] and empty["total"] == 0


def test_admin_users_list(client, admin_h, user_h):
    users = client.get(f"{API}/admin/users", headers=admin_h).json()
    assert any(u["email"] == "admin@udyam.local" and u["role"] == "admin" for u in users)
    assert all("password" not in u and "password_hash" not in u for u in users)
    assert client.get(f"{API}/admin/users", headers=user_h).status_code == 403
