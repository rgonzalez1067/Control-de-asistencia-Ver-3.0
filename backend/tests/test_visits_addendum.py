"""Backend tests for iteration 14 addendum: is_minor + close visit."""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "admin123"
EMPLOYEE_EMAIL = "jgil@megasoft.com.ve"
EMPLOYEE_PASSWORD = "TestPass!234"

_created_visit_ids = []


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def admin_user_id(admin):
    return admin.get(f"{API}/auth/me").json()["user_id"]


@pytest.fixture(scope="module")
def employee_no_perms(admin):
    """Ensure jgil exists w/o can_view_visit_logs, and return logged-in session."""
    users = admin.get(f"{API}/users").json()
    emp = next((u for u in users if u.get("email") == EMPLOYEE_EMAIL), None)
    assert emp, f"{EMPLOYEE_EMAIL} not found"
    admin.post(f"{API}/auth/reset-password",
               json={"user_id": emp["user_id"], "new_password": EMPLOYEE_PASSWORD})
    admin.post(f"{API}/users/{emp['user_id']}/visit-permissions",
               json={"can_create_visits": False, "can_view_visit_logs": False})
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    r = s.post(f"{API}/auth/login", json={"email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PASSWORD})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def _track(vid):
    _created_visit_ids.append(vid)
    return vid


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin):
    yield
    for vid in _created_visit_ids:
        try:
            admin.delete(f"{API}/visits/{vid}")
        except Exception:
            pass


# ---------- is_minor validation ----------

class TestIsMinor:
    def test_personal_minor_no_cedula_accepted(self, admin, admin_user_id):
        r = admin.post(f"{API}/visits", json={
            "type": "personal",
            "host_user_id": admin_user_id,
            "visitors": [{"name": "TEST_MinorChild", "is_minor": True}],
        })
        assert r.status_code in (200, 201), r.text
        vid = r.json()["visit_id"]
        _track(vid)
        # Verify persisted
        g = admin.get(f"{API}/visits/{vid}").json()
        assert g["visitors"][0]["is_minor"] is True
        assert g["visitors"][0].get("cedula") in (None, "")

    def test_personal_minor_null_cedula_accepted(self, admin, admin_user_id):
        r = admin.post(f"{API}/visits", json={
            "type": "personal",
            "host_user_id": admin_user_id,
            "visitors": [{"name": "TEST_MinorNull", "cedula": None, "is_minor": True}],
        })
        assert r.status_code in (200, 201), r.text
        _track(r.json()["visit_id"])

    def test_personal_not_minor_no_cedula_rejected(self, admin, admin_user_id):
        r = admin.post(f"{API}/visits", json={
            "type": "personal",
            "host_user_id": admin_user_id,
            "visitors": [{"name": "TEST_Adult", "is_minor": False}],
        })
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Cédula" in detail or "cédula" in detail
        assert "menor" in detail.lower()

    def test_personal_absent_is_minor_no_cedula_rejected(self, admin, admin_user_id):
        r = admin.post(f"{API}/visits", json={
            "type": "personal",
            "host_user_id": admin_user_id,
            "visitors": [{"name": "TEST_AdultAbsent"}],
        })
        assert r.status_code == 400

    def test_laboral_requires_cedula_even_if_minor_flag(self, admin, admin_user_id):
        r = admin.post(f"{API}/visits", json={
            "type": "laboral",
            "host_user_id": admin_user_id,
            "company_name": "TEST_CoMinor",
            "visitors": [{"name": "TEST_NoCed", "phone": "0414", "is_minor": True}],
        })
        assert r.status_code == 400
        assert "cédula" in r.json().get("detail", "").lower()

    def test_laboral_no_phone_rejected(self, admin, admin_user_id):
        r = admin.post(f"{API}/visits", json={
            "type": "laboral",
            "host_user_id": admin_user_id,
            "company_name": "TEST_CoPhone",
            "visitors": [{"name": "TEST_NoPhone", "cedula": "V1"}],
        })
        assert r.status_code == 400
        assert "teléfono" in r.json().get("detail", "").lower() or "phone" in r.json().get("detail", "").lower()


# ---------- close_visit endpoint ----------

class TestCloseVisit:
    def _make_visit(self, admin, admin_user_id, scheduled_at=None):
        payload = {
            "type": "personal",
            "host_user_id": admin_user_id,
            "visitors": [{"name": "TEST_Close", "cedula": "V-CLOSE"}],
        }
        if scheduled_at:
            payload["scheduled_at"] = scheduled_at
        r = admin.post(f"{API}/visits", json=payload)
        assert r.status_code in (200, 201), r.text
        vid = r.json()["visit_id"]
        _track(vid)
        return vid

    def test_close_success(self, admin, admin_user_id):
        vid = self._make_visit(admin, admin_user_id)
        r = admin.post(f"{API}/visits/{vid}/close")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "exit_at" in data and data["exit_at"]
        assert "duration_minutes" in data
        assert isinstance(data["duration_minutes"], (int, float))

    def test_close_already_closed(self, admin, admin_user_id):
        vid = self._make_visit(admin, admin_user_id)
        r1 = admin.post(f"{API}/visits/{vid}/close")
        assert r1.status_code == 200
        r2 = admin.post(f"{API}/visits/{vid}/close")
        assert r2.status_code == 400
        assert "cerrada" in r2.json().get("detail", "").lower()

    def test_close_not_found(self, admin):
        r = admin.post(f"{API}/visits/visit_nope_xxx/close")
        assert r.status_code == 404

    def test_close_no_permission(self, employee_no_perms, admin, admin_user_id):
        vid = self._make_visit(admin, admin_user_id)
        r = employee_no_perms.post(f"{API}/visits/{vid}/close")
        assert r.status_code == 403

    def test_get_visit_after_close_has_fields(self, admin, admin_user_id):
        vid = self._make_visit(admin, admin_user_id)
        admin.post(f"{API}/visits/{vid}/close")
        g = admin.get(f"{API}/visits/{vid}")
        assert g.status_code == 200
        d = g.json()
        assert d["status"] == "closed"
        assert d.get("exit_at")
        assert isinstance(d.get("duration_minutes"), (int, float))
        assert d.get("closed_by")

    def test_duration_calculation_approx_30min(self, admin, admin_user_id):
        # scheduled_at = now - 30 minutes (UTC ISO)
        past = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        vid = self._make_visit(admin, admin_user_id, scheduled_at=past)
        r = admin.post(f"{API}/visits/{vid}/close")
        assert r.status_code == 200
        dur = r.json()["duration_minutes"]
        assert dur is not None
        assert 29 <= dur <= 31, f"Expected ~30, got {dur}"
