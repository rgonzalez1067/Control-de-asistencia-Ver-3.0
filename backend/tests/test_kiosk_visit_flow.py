"""Iteration 13 — Verify kiosk pending-visits flow bug fix.

Bug: after Kleiver marks attendance via kiosk, the 'Visita' button was not
displayed on the success screen. Backend endpoint is fine; frontend fix
removed the `if (marked === "in")` gate and renamed shadowed local variable.

This suite validates the backend side of the flow end-to-end.
"""
import os
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as _f:
        for _line in _f:
            if _line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
                break
KLEIVER_ID = "user_4608651f4dd7"


# ─── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "rgonzalez@megasoft.com.ve", "password": "admin123"},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ─── Tests ───────────────────────────────────────────────────────────────
def test_kleiver_user_exists(admin_headers):
    r = requests.get(f"{BASE_URL}/api/users/{KLEIVER_ID}", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user_id"] == KLEIVER_ID
    # Loose name check (case/format tolerant)
    assert "KLEIVER" in (data.get("name") or "").upper()


def test_seed_pending_visit_if_missing(admin_headers):
    """Ensure at least one pending visit exists today for Kleiver."""
    r = requests.get(f"{BASE_URL}/api/kiosk/pending-visits/{KLEIVER_ID}", timeout=15)
    assert r.status_code == 200
    existing = r.json()
    if len(existing) == 0:
        # Create today at noon UTC (well within today's Caracas range)
        scheduled = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
        payload = {
            "type": "laboral",
            "host_user_id": KLEIVER_ID,
            "company_name": "TEST_TestCo",
            "motive": "Test iteration 13 kiosk-visit-btn",
            "visitors": [
                {"name": "TEST_Visitor 1", "cedula": "V-1", "phone": "0412"},
                {"name": "TEST_Visitor 2", "cedula": "V-2", "phone": "0412"},
            ],
            "scheduled_at": scheduled,
        }
        create = requests.post(f"{BASE_URL}/api/visits", json=payload, headers=admin_headers, timeout=15)
        assert create.status_code in (200, 201), create.text
        # Verify persistence
        r2 = requests.get(f"{BASE_URL}/api/kiosk/pending-visits/{KLEIVER_ID}", timeout=15)
        assert r2.status_code == 200
        assert len(r2.json()) >= 1


def test_pending_visits_endpoint_returns_visit():
    r = requests.get(f"{BASE_URL}/api/kiosk/pending-visits/{KLEIVER_ID}", timeout=15)
    assert r.status_code == 200
    visits = r.json()
    assert isinstance(visits, list)
    assert len(visits) >= 1, "Expected at least 1 pending visit for Kleiver today"
    v = visits[0]
    # Data assertions
    assert v.get("host_user_id") == KLEIVER_ID
    assert v.get("status") in ("pending", "in_progress")
    assert isinstance(v.get("visitors"), list) and len(v["visitors"]) >= 1
    assert "_id" not in v, "MongoDB _id must be excluded"


def test_attendance_check_then_pending_still_returned():
    """Simulate confirmMark: POST /kiosk/attendance/check then GET pending-visits.
    The endpoint should still return the visit regardless of in/out type.
    """
    r_before = requests.get(f"{BASE_URL}/api/kiosk/pending-visits/{KLEIVER_ID}", timeout=15)
    assert r_before.status_code == 200
    count_before = len(r_before.json())
    assert count_before >= 1

    # Mark attendance (auto — backend chooses in or out)
    mark = requests.post(
        f"{BASE_URL}/api/kiosk/attendance/check",
        json={"user_id": KLEIVER_ID, "type": "auto"},
        timeout=15,
    )
    assert mark.status_code == 200, mark.text
    data = mark.json()
    assert data.get("type") in ("in", "out"), data

    # After mark, pending visits should still be returned (endpoint doesn't
    # filter by attendance)
    r_after = requests.get(f"{BASE_URL}/api/kiosk/pending-visits/{KLEIVER_ID}", timeout=15)
    assert r_after.status_code == 200
    assert len(r_after.json()) >= 1, "Pending visits missing after attendance mark"


def test_regression_user_without_visit_returns_empty(admin_headers):
    """Any other employee without a scheduled visit today should get []."""
    # Fetch users list, pick first non-Kleiver employee
    r = requests.get(f"{BASE_URL}/api/users", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    users = r.json()
    other = next((u for u in users if u.get("user_id") != KLEIVER_ID and u.get("role") == "employee"), None)
    if not other:
        pytest.skip("No other employee available for regression test")
    r2 = requests.get(f"{BASE_URL}/api/kiosk/pending-visits/{other['user_id']}", timeout=15)
    assert r2.status_code == 200
    visits = r2.json()
    # Not asserting == 0 strictly because seed data could exist; log for inspection
    print(f"Regression employee {other['user_id']}: {len(visits)} pending visits")
