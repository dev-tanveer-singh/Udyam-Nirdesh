import os
import tempfile
from pathlib import Path

# Configure BEFORE the app is imported (settings are read at import time).
_tmp = Path(tempfile.mkdtemp(prefix="udyam-tests-"))
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=f"sqlite:///{_tmp / 'test.db'}",
    UPLOAD_DIR=str(_tmp / "uploads"),
    SERVE_FRONTEND="false",
    SECRET_KEY="test-secret-key-test-secret-key-test-secret-key",
    ADMIN_PASSWORD="admin-test-pass",
    SEED_DEMO_USER="true",
)

import itertools  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.security import login_throttle  # noqa: E402

API = "/api/v1"
_counter = itertools.count(1)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_throttle():
    login_throttle.reset()


def make_user(client, role="user", password="password123"):
    email = f"u{next(_counter)}@example.com"
    r = client.post(f"{API}/auth/register", json={"full_name": "Test User", "email": email, "password": password, "role": role})
    assert r.status_code == 201, r.text
    return email, password


def auth_headers(client, email, password):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def user_h(client):
    return auth_headers(client, *make_user(client))


@pytest.fixture
def admin_h(client):
    return auth_headers(client, "admin@udyam.local", "admin-test-pass")


FULL_PROFILE = {
    "full_name": "Aman Kumar", "age": 24, "gender": "Male", "state": "Punjab", "district": "Ludhiana",
    "category": "OBC", "occupation": "Student", "business_type": "Manufacturing", "business_stage": "New Business",
    "annual_income": 350000, "annual_turnover": 800000, "funding_required": 800000,
    "own_contribution": 80000, "funding_purpose": "Machinery",
}


# Aliases used by tests/test_api.py
@pytest.fixture
def user(user_h):
    return user_h


@pytest.fixture
def admin(admin_h):
    return admin_h


@pytest.fixture(scope="module", autouse=True)
def _fresh_database(client):
    """Every test module starts from the pristine seed data (3 schemes, 6 partners, demo accounts),
    so tests that create or edit reference data cannot affect each other across files."""
    from app.database import Base, engine
    from app.seed import run_seed

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_seed()
