from .conftest import API, FULL_PROFILE, auth_headers, make_user


def test_register_login_me(client):
    email, pw = make_user(client)
    h = auth_headers(client, email, pw)
    me = client.get(f"{API}/auth/me", headers=h).json()
    assert me["email"] == email and me["role"] == "user" and len(me["id"]) == 32
    assert "password" not in str(me).lower()


def test_login_response_shape(client):
    email, pw = make_user(client)
    body = client.post(f"{API}/auth/login", json={"email": email, "password": pw}).json()
    assert body["token_type"] == "bearer" and body["expires_in"] > 0
    assert set(body["user"]) == {"id", "full_name", "email", "role", "created_at"}
    assert body["user"]["created_at"].endswith("Z") or "+00:00" in body["user"]["created_at"]


def test_duplicate_email_and_weak_password(client):
    email, _ = make_user(client)
    dup = client.post(f"{API}/auth/register", json={"full_name": "X", "email": email.upper(), "password": "password123"})
    assert dup.status_code == 409
    weak = client.post(f"{API}/auth/register", json={"full_name": "X", "email": "w@example.com", "password": "short"})
    assert weak.status_code == 422


def test_cannot_self_register_as_admin(client):
    r = client.post(f"{API}/auth/register", json={"full_name": "X", "email": "evil@example.com", "password": "password123", "role": "admin"})
    assert r.status_code == 422


def test_bad_login_and_throttle(client):
    email, _ = make_user(client)
    for _ in range(10):
        assert client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 429


def test_requires_token(client):
    assert client.get(f"{API}/profile").status_code == 401
    assert client.get(f"{API}/profile", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_demo_accounts_seeded(client):
    assert client.post(f"{API}/auth/login", json={"email": "user@udyam.local", "password": "user123"}).status_code == 200


def test_profile_roundtrip_keeps_numbers_as_numbers(client, user_h):
    empty = client.get(f"{API}/profile", headers=user_h).json()
    assert empty["age"] is None and empty["full_name"] is None
    r = client.put(f"{API}/profile", json=FULL_PROFILE, headers=user_h)
    assert r.status_code == 200, r.text
    got = client.get(f"{API}/profile", headers=user_h).json()
    assert got["age"] == 24 and isinstance(got["age"], int)
    assert got["annual_income"] == 350000 and isinstance(got["annual_income"], (int, float))
    assert got["business_type"] == "Manufacturing"


def test_profile_blank_strings_become_null(client, user_h):
    r = client.put(f"{API}/profile", json={**FULL_PROFILE, "district": "  ", "own_contribution": ""}, headers=user_h)
    assert r.status_code == 200
    assert r.json()["district"] is None and r.json()["own_contribution"] is None


def test_profile_validation(client, user_h):
    bad = lambda **kw: client.put(f"{API}/profile", json={**FULL_PROFILE, **kw}, headers=user_h).status_code
    assert bad(age=17) == 422
    assert bad(age=24.5) == 422
    assert bad(age="abc") == 422
    assert bad(category="Martian") == 422
    assert bad(annual_income=-1) == 422
    assert client.put(f"{API}/profile", json={**FULL_PROFILE, "fullName": "typo"}, headers=user_h).status_code == 422


def test_profile_is_entrepreneur_only(client, admin_h):
    assert client.get(f"{API}/profile", headers=admin_h).status_code == 403


def test_profiles_are_isolated(client):
    a = auth_headers(client, *make_user(client))
    b = auth_headers(client, *make_user(client))
    client.put(f"{API}/profile", json=FULL_PROFILE, headers=a)
    assert client.get(f"{API}/profile", headers=b).json()["age"] is None


def test_meta_is_public(client):
    m = client.get(f"{API}/meta").json()
    assert "Punjab" in m["states"] and {"type": "pan", "label": "PAN"} in m["document_types"]
    assert [s["value"] for s in m["application_statuses"]][:2] == ["not_started", "documents_pending"]
