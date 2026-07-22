"""
MegaSoft Asistencia — Backend regression tests.

Covers 47 endpoints across:
  Auth · Users · Settings · Sites · Departments · Schedules ·
  Kiosk · Attendance · Novelties · Reports/Stats · Onboarding · Root
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://asistencia-web-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "admin123"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["role"] == "admin"
    return data["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Root / Health
# ---------------------------------------------------------------------------
class TestRoot:
    def test_root(self, api):
        r = api.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("service") == "megasoft-asistencia"
        assert data.get("status") == "ok"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class TestAuth:
    def test_login_success(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["role"] == "admin"
        assert isinstance(d["token"], str)
        assert "password_hash" not in d["user"]

    def test_login_invalid(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": "wrongpwd"})
        assert r.status_code == 401

    def test_me_with_token(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN_EMAIL
        assert d["role"] == "admin"

    def test_me_without_token(self, api):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_logout(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/auth/logout", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_needs_bootstrap(self, api):
        r = api.get(f"{BASE_URL}/api/auth/needs-bootstrap")
        assert r.status_code == 200
        assert r.json() == {"needs_bootstrap": False}

    def test_change_password_and_revert(self, api):
        # Login fresh
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        token = r.json()["token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        new_pw = "tempPass_9182"
        r = api.post(f"{BASE_URL}/api/auth/change-password",
                     headers=headers,
                     json={"old_password": ADMIN_PASSWORD, "new_password": new_pw})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # Login with new
        r2 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": new_pw})
        assert r2.status_code == 200

        # Revert
        token2 = r2.json()["token"]
        headers2 = {"Authorization": f"Bearer {token2}", "Content-Type": "application/json"}
        r3 = api.post(f"{BASE_URL}/api/auth/change-password",
                      headers=headers2,
                      json={"old_password": new_pw, "new_password": ADMIN_PASSWORD})
        assert r3.status_code == 200

        # Verify revert works
        r4 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r4.status_code == 200

    def test_reset_password_admin(self, api, auth_headers):
        # Create test user, then reset its password
        create = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": "TEST_reset@example.com",
            "name": "TEST Reset",
            "role": "employee",
            "password": "initial123",
        })
        assert create.status_code == 200
        uid = create.json()["user_id"]

        # Reset via admin
        r = api.post(f"{BASE_URL}/api/auth/reset-password", headers=auth_headers,
                     json={"user_id": uid, "new_password": "resetted456"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # Login with reset password
        rl = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "TEST_reset@example.com", "password": "resetted456"})
        assert rl.status_code == 200

        # Cleanup
        api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_reset_password_404(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/auth/reset-password", headers=auth_headers,
                     json={"user_id": "nonexistent_id_xyz", "new_password": "abc12345"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class TestUsers:
    def test_users_list(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/users", headers=auth_headers)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        assert len(users) >= 17
        # Ensure sensitive fields excluded
        for u in users:
            assert "password_hash" not in u
            assert "pin_code_hash" not in u
            assert "selfie_base64" not in u
            assert "face_descriptor" not in u
            assert "_id" not in u

    def test_users_crud_flow(self, api, auth_headers):
        email = f"TEST_user_{int(time.time())}@example.com"
        # Create
        r = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST User", "role": "employee", "password": "pw12345"
        })
        assert r.status_code == 200
        uid = r.json()["user_id"]
        assert r.json()["email"] == email.lower()
        email_lc = email.lower()

        # 409 duplicate
        rdup = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "Dup", "role": "employee"
        })
        assert rdup.status_code == 409

        # Get
        rg = api.get(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
        assert rg.status_code == 200
        assert rg.json()["email"] == email_lc

        # Update
        ru = api.put(f"{BASE_URL}/api/users/{uid}", headers=auth_headers, json={"name": "nuevo"})
        assert ru.status_code == 200
        assert ru.json()["name"] == "nuevo"

        # Update 404
        r404 = api.put(f"{BASE_URL}/api/users/nonexistent_zzz",
                       headers=auth_headers, json={"name": "x"})
        assert r404.status_code == 404

        # Delete
        rd = api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
        assert rd.status_code == 200

        # Verify 404 after delete
        rget2 = api.get(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
        assert rget2.status_code == 404

    def test_users_import_template(self, api, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/users/import/template", headers=h)
        assert r.status_code == 200
        text = r.text
        assert "email" in text and "name" in text and "role" in text

    def test_users_import_csv(self, api, admin_token, auth_headers):
        h = {"Authorization": f"Bearer {admin_token}"}
        email = f"TEST_csv_{int(time.time())}@example.com"
        csv_content = (
            "email,name,cedula,role,position,department_id,site_id,supervisor_id,schedule_id,password\n"
            f"{email},TEST CSV,V12345,employee,Analista,,,,,pw12345\n"
        )
        files = {"file": ("t.csv", csv_content, "text/csv")}
        r = requests.post(f"{BASE_URL}/api/users/import", headers=h, files=files)
        assert r.status_code == 200
        d = r.json()
        assert d["created"] == 1
        assert "skipped" in d and "errors" in d

        # Cleanup
        users = api.get(f"{BASE_URL}/api/users", headers=auth_headers).json()
        for u in users:
            if u["email"] == email:
                api.delete(f"{BASE_URL}/api/users/{u['user_id']}", headers=auth_headers)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class TestSettings:
    def test_settings_get_and_put_revert(self, api, auth_headers):
        rg = api.get(f"{BASE_URL}/api/settings")
        assert rg.status_code == 200
        original = rg.json().get("name")

        r = api.put(f"{BASE_URL}/api/settings", headers=auth_headers, json={"name": "Test"})
        assert r.status_code == 200
        assert r.json()["name"] == "Test"

        # Revert
        revert_name = original or "Mega Soft Computación, C.A."
        rv = api.put(f"{BASE_URL}/api/settings", headers=auth_headers, json={"name": revert_name})
        assert rv.status_code == 200


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------
class TestSites:
    def test_sites_list_and_crud(self, api, auth_headers):
        rl = api.get(f"{BASE_URL}/api/sites", headers=auth_headers)
        assert rl.status_code == 200
        sites = rl.json()
        assert isinstance(sites, list)
        assert len(sites) >= 2

        rc = api.post(f"{BASE_URL}/api/sites", headers=auth_headers, json={
            "name": "TEST Site", "address": "Addr", "latitude": 10.5, "longitude": -66.9,
            "radius_meters": 150,
        })
        assert rc.status_code == 200
        sid = rc.json()["site_id"]

        ru = api.put(f"{BASE_URL}/api/sites/{sid}", headers=auth_headers, json={
            "name": "TEST Site 2", "latitude": 10.5, "longitude": -66.9, "radius_meters": 200
        })
        assert ru.status_code == 200
        assert ru.json()["name"] == "TEST Site 2"

        rd = api.delete(f"{BASE_URL}/api/sites/{sid}", headers=auth_headers)
        assert rd.status_code == 200

    def test_sites_resolve_link(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/sites/resolve-link", headers=auth_headers,
                     json={"link": "https://maps.google.com/?q=10.4936,-66.8779"})
        assert r.status_code == 200
        d = r.json()
        assert abs(d["latitude"] - 10.4936) < 1e-4
        assert abs(d["longitude"] - (-66.8779)) < 1e-4


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
class TestDepartments:
    def test_departments_list_and_crud(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/departments", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 15

        rc = api.post(f"{BASE_URL}/api/departments", headers=auth_headers,
                      json={"name": "TEST Dept", "description": "d"})
        assert rc.status_code == 200
        did = rc.json()["department_id"]

        ru = api.put(f"{BASE_URL}/api/departments/{did}", headers=auth_headers,
                     json={"name": "TEST Dept 2"})
        assert ru.status_code == 200
        assert ru.json()["name"] == "TEST Dept 2"

        rd = api.delete(f"{BASE_URL}/api/departments/{did}", headers=auth_headers)
        assert rd.status_code == 200


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
class TestSchedules:
    def test_schedules_list_and_create(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/schedules", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 5

        rc = api.post(f"{BASE_URL}/api/schedules", headers=auth_headers, json={
            "name": "TEST Schedule",
            "blocks": [{"start": "09:00", "end": "17:00"}],
            "tolerance_minutes": 10,
        })
        assert rc.status_code == 200
        sid = rc.json()["schedule_id"]
        # Cleanup
        api.delete(f"{BASE_URL}/api/schedules/{sid}", headers=auth_headers)


# ---------------------------------------------------------------------------
# Kiosk
# ---------------------------------------------------------------------------
class TestKiosk:
    def test_kiosk_unlock_admin(self, api):
        r = api.post(f"{BASE_URL}/api/kiosk/unlock",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "unlocked_by" in d

    def test_kiosk_unlock_employee_denied(self, api, auth_headers):
        # Create test employee
        email = f"TEST_kiosk_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST Emp", "role": "employee", "password": "pw12345"
        })
        assert rc.status_code == 200
        uid = rc.json()["user_id"]

        r = api.post(f"{BASE_URL}/api/kiosk/unlock",
                     json={"email": email, "password": "pw12345"})
        assert r.status_code == 401

        api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_kiosk_roster(self, api):
        r = api.get(f"{BASE_URL}/api/kiosk/roster")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
class TestAttendance:
    def test_attendance_check_me_today(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/attendance/check", headers=auth_headers,
                     json={"type": "in", "latitude": 10.4936, "longitude": -66.8779})
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "in"
        assert "is_late" in d
        assert "record_id" in d
        rec_id = d["record_id"]

        # attendance/me should include it
        rm = api.get(f"{BASE_URL}/api/attendance/me", headers=auth_headers)
        assert rm.status_code == 200
        ids = [x["record_id"] for x in rm.json()]
        assert rec_id in ids

        # attendance/today
        rt = api.get(f"{BASE_URL}/api/attendance/today", headers=auth_headers)
        assert rt.status_code == 200
        assert isinstance(rt.json(), list)

    def test_attendance_team_admin(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/attendance/team", headers=auth_headers)
        assert r.status_code == 200

    def test_attendance_team_employee_forbidden(self, api, auth_headers):
        email = f"TEST_emp_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]

        # Login as employee
        rl = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": "pw12345"})
        assert rl.status_code == 200
        emp_token = rl.json()["token"]
        h = {"Authorization": f"Bearer {emp_token}"}
        r = api.get(f"{BASE_URL}/api/attendance/team", headers=h)
        assert r.status_code == 403

        api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)


# ---------------------------------------------------------------------------
# Novelties
# ---------------------------------------------------------------------------
class TestNovelties:
    def test_novelties_full_cycle(self, api, auth_headers):
        rl = api.get(f"{BASE_URL}/api/novelties", headers=auth_headers)
        assert rl.status_code == 200

        rc = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
            "type": "permission",
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
            "reason": "test"
        })
        assert rc.status_code == 200
        d = rc.json()
        assert d["status"] == "pending"
        nid = d["novelty_id"]

        # Bulk decide -> approved
        rd = api.post(f"{BASE_URL}/api/novelties/bulk-decide", headers=auth_headers,
                      json={"novelty_ids": [nid], "decision": "approved"})
        assert rd.status_code == 200
        assert rd.json()["updated"] == 1

        # Delete (admin can delete without status filter)
        rdel = api.delete(f"{BASE_URL}/api/novelties/{nid}", headers=auth_headers)
        assert rdel.status_code == 200


# ---------------------------------------------------------------------------
# Stats / Reports
# ---------------------------------------------------------------------------
class TestStatsReports:
    def test_stats_dashboard(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/stats/dashboard", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        for k in ["total_users", "onboarded_users", "check_ins_today",
                  "late_today", "pending_novelties", "series_7d"]:
            assert k in d
        assert len(d["series_7d"]) == 7

    def test_reports_list(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/reports", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_reports_list_with_range(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/reports?from_date=2026-01-01&to_date=2026-12-31",
                    headers=auth_headers)
        assert r.status_code == 200

    def test_reports_employee_forbidden(self, api, auth_headers):
        email = f"TEST_repemp_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]

        rl = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": "pw12345"})
        h = {"Authorization": f"Bearer {rl.json()['token']}"}
        r = api.get(f"{BASE_URL}/api/reports", headers=h)
        assert r.status_code == 403

        api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_reports_export_csv(self, api, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/reports/export", headers=h)
        assert r.status_code == 200
        text = r.text
        assert "record_id" in text
        assert "user_id" in text
        assert "timestamp_utc" in text


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
class TestOnboarding:
    def test_onboarding_selfie(self, api, auth_headers):
        # Create test user, login as them, upload selfie
        email = f"TEST_onb_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]

        rl = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": "pw12345"})
        emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                 "Content-Type": "application/json"}

        r = api.post(f"{BASE_URL}/api/onboarding/selfie", headers=emp_h,
                     json={"selfie_base64": "data:image/jpeg;base64,AAAA"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # Verify onboarded=true
        rg = api.get(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
        assert rg.json().get("onboarded") is True

        api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
