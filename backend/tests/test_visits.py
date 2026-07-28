"""Backend tests for Control de Visitas (iteration 12).

Covers:
- POST /users/{user_id}/visit-permissions (admin only)
- POST /visits (personal + laboral validation + permission gating)
- GET /visits (permission gating)
- GET /kiosk/pending-visits/{host_user_id} (today only)
- POST /visits/{visit_id}/capture-selfie (sequential capture)
"""
import os
import pytest
import requests
from datetime import datetime, timedelta

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "admin123"

EMPLOYEE_PASSWORD = "TestPass!234"

TINY_JPEG_B64 = (
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQ"
    "gKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAU"
    "EAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAA"
    "AAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A/9k="
)

# ---------------- Helpers / Fixtures ----------------


def _login(session: requests.Session, email: str, password: str):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    return r


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="module")
def employee(admin_session):
    """Pick a non-admin user and reset their password so we can log in."""
    r = admin_session.get(f"{API}/users")
    assert r.status_code == 200, r.text
    users = r.json()
    emp = next(
        (u for u in users if u.get("role") == "employee" and u.get("email")),
        None,
    )
    assert emp, "No employee user found in DB"
    # Reset password via admin endpoint so we can login
    rr = admin_session.post(
        f"{API}/auth/reset-password",
        json={"user_id": emp["user_id"], "new_password": EMPLOYEE_PASSWORD},
    )
    assert rr.status_code == 200, rr.text
    # Ensure permissions start false
    admin_session.post(
        f"{API}/users/{emp['user_id']}/visit-permissions",
        json={"can_create_visits": False, "can_view_visit_logs": False},
    )
    return emp


def _emp_session(employee):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = _login(s, employee["email"], EMPLOYEE_PASSWORD)
    assert r.status_code == 200, f"Employee login failed: {r.text}"
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


# ---------------- Tests ----------------


class TestVisitPermissions:
    def test_admin_sets_permissions(self, admin_session, employee):
        r = admin_session.post(
            f"{API}/users/{employee['user_id']}/visit-permissions",
            json={"can_create_visits": True, "can_view_visit_logs": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        # Verify persistence via GET /users
        u = admin_session.get(f"{API}/users").json()
        target = next(x for x in u if x["user_id"] == employee["user_id"])
        assert target.get("can_create_visits") is True
        assert target.get("can_view_visit_logs") is True

    def test_non_admin_cannot_set_permissions(self, admin_session, employee):
        # Give the employee create rights first so login works, then try
        admin_session.post(
            f"{API}/users/{employee['user_id']}/visit-permissions",
            json={"can_create_visits": True, "can_view_visit_logs": True},
        )
        emp_s = _emp_session(employee)
        r = emp_s.post(
            f"{API}/users/{employee['user_id']}/visit-permissions",
            json={"can_create_visits": True},
        )
        assert r.status_code == 403, r.text


class TestVisitCreation:
    def test_create_personal_visit_admin(self, admin_session):
        # Get an admin user_id to use as host
        me = admin_session.get(f"{API}/auth/me").json()
        payload = {
            "type": "personal",
            "host_user_id": me["user_id"],
            "visitors": [{"name": "TEST_Visitor", "cedula": "V12345678"}],
        }
        r = admin_session.post(f"{API}/visits", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["visit_id"].startswith("visit")
        # Verify via list
        lst = admin_session.get(f"{API}/visits").json()
        assert any(v["visit_id"] == data["visit_id"] for v in lst)
        # And via get
        g = admin_session.get(f"{API}/visits/{data['visit_id']}")
        assert g.status_code == 200
        gd = g.json()
        assert gd["type"] == "personal"
        assert gd["visitors"][0]["cedula"] == "V12345678"
        pytest.visit_id_personal = data["visit_id"]

    def test_laboral_requires_company(self, admin_session):
        me = admin_session.get(f"{API}/auth/me").json()
        r = admin_session.post(
            f"{API}/visits",
            json={
                "type": "laboral",
                "host_user_id": me["user_id"],
                "visitors": [{"name": "X", "cedula": "V1", "phone": "0414"}],
            },
        )
        assert r.status_code == 400

    def test_laboral_requires_phone(self, admin_session):
        me = admin_session.get(f"{API}/auth/me").json()
        r = admin_session.post(
            f"{API}/visits",
            json={
                "type": "laboral",
                "host_user_id": me["user_id"],
                "company_name": "TEST_Corp",
                "visitors": [{"name": "X", "cedula": "V1"}],
            },
        )
        assert r.status_code == 400

    def test_empty_visitors(self, admin_session):
        me = admin_session.get(f"{API}/auth/me").json()
        r = admin_session.post(
            f"{API}/visits",
            json={"type": "personal", "host_user_id": me["user_id"], "visitors": []},
        )
        assert r.status_code == 400


class TestVisitPermissionEnforcement:
    def test_employee_without_permission_403(self, admin_session, employee):
        # Revoke perms
        admin_session.post(
            f"{API}/users/{employee['user_id']}/visit-permissions",
            json={"can_create_visits": False, "can_view_visit_logs": False},
        )
        emp_s = _emp_session(employee)
        r = emp_s.post(
            f"{API}/visits",
            json={
                "type": "personal",
                "host_user_id": employee["user_id"],
                "visitors": [{"name": "X", "cedula": "V1"}],
            },
        )
        assert r.status_code == 403
        # list also blocked
        r2 = emp_s.get(f"{API}/visits")
        assert r2.status_code == 403

    def test_employee_with_permission_can_create(self, admin_session, employee):
        admin_session.post(
            f"{API}/users/{employee['user_id']}/visit-permissions",
            json={"can_create_visits": True, "can_view_visit_logs": True},
        )
        emp_s = _emp_session(employee)
        r = emp_s.post(
            f"{API}/visits",
            json={
                "type": "personal",
                "host_user_id": employee["user_id"],
                "visitors": [{"name": "TEST_V", "cedula": "V9"}],
            },
        )
        assert r.status_code == 200, r.text
        r2 = emp_s.get(f"{API}/visits")
        assert r2.status_code == 200


class TestKioskPendingVisits:
    def test_today_visit_returned_tomorrow_not(self, admin_session):
        me = admin_session.get(f"{API}/auth/me").json()
        host_id = me["user_id"]

        # Create for today
        r_today = admin_session.post(
            f"{API}/visits",
            json={
                "type": "personal",
                "host_user_id": host_id,
                "scheduled_at": datetime.utcnow().isoformat(),
                "visitors": [{"name": "TEST_Today", "cedula": "V-TODAY"}],
            },
        )
        assert r_today.status_code == 200, r_today.text
        today_id = r_today.json()["visit_id"]

        # Create for tomorrow
        tomorrow = (datetime.utcnow() + timedelta(days=2)).isoformat()
        r_tom = admin_session.post(
            f"{API}/visits",
            json={
                "type": "personal",
                "host_user_id": host_id,
                "scheduled_at": tomorrow,
                "visitors": [{"name": "TEST_Tom", "cedula": "V-TOM"}],
            },
        )
        assert r_tom.status_code == 200
        tom_id = r_tom.json()["visit_id"]

        # Kiosk endpoint is public
        pub = requests.get(f"{API}/kiosk/pending-visits/{host_id}")
        assert pub.status_code == 200, pub.text
        ids = [v["visit_id"] for v in pub.json()]
        assert today_id in ids
        assert tom_id not in ids


class TestSelfieCapture:
    def test_sequential_capture_completes(self, admin_session):
        me = admin_session.get(f"{API}/auth/me").json()
        # Create laboral with 2 visitors
        r = admin_session.post(
            f"{API}/visits",
            json={
                "type": "laboral",
                "host_user_id": me["user_id"],
                "company_name": "TEST_SelfieCorp",
                "motive": "Reunión",
                "visitors": [
                    {"name": "V1", "cedula": "V-01", "phone": "0414-1111111"},
                    {"name": "V2", "cedula": "V-02", "phone": "0414-2222222"},
                ],
            },
        )
        assert r.status_code == 200, r.text
        vid = r.json()["visit_id"]

        # Invalid base64 (missing data: prefix)
        bad = requests.post(
            f"{API}/visits/{vid}/capture-selfie",
            json={"visitor_index": 0, "selfie_base64": "notvalid"},
        )
        assert bad.status_code == 400

        # Out of range
        oor = requests.post(
            f"{API}/visits/{vid}/capture-selfie",
            json={"visitor_index": 5, "selfie_base64": TINY_JPEG_B64},
        )
        assert oor.status_code == 400

        # First visitor
        c0 = requests.post(
            f"{API}/visits/{vid}/capture-selfie",
            json={"visitor_index": 0, "selfie_base64": TINY_JPEG_B64},
        )
        assert c0.status_code == 200, c0.text
        d0 = c0.json()
        assert d0["status"] == "in_progress"
        assert d0["captured"] == 1

        # Second visitor
        c1 = requests.post(
            f"{API}/visits/{vid}/capture-selfie",
            json={"visitor_index": 1, "selfie_base64": TINY_JPEG_B64},
        )
        assert c1.status_code == 200, c1.text
        d1 = c1.json()
        assert d1["status"] == "completed"
        assert d1["captured"] == 2

        # Verify completed_at set via GET
        g = admin_session.get(f"{API}/visits/{vid}").json()
        assert g["status"] == "completed"
        assert g.get("completed_at") is not None
