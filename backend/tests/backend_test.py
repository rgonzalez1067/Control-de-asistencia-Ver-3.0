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

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://asistencia-web-1.preview.emergentagent.com").rstrip("/")

# Read frontend/.env if REACT_APP_BACKEND_URL missing in environment
if "REACT_APP_BACKEND_URL" not in os.environ:
    _envp = "/app/frontend/.env"
    if os.path.exists(_envp):
        with open(_envp) as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = _line.split("=", 1)[1].strip().rstrip("/")
                    break
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


# ---------------------------------------------------------------------------
# Iteration 2 — Geofence removed, Sites optional lat/lng, Users photo endpoint
# ---------------------------------------------------------------------------
class TestGeofenceRemoved:
    """POST /api/attendance/check must not compute within_geofence (should be None)."""

    def test_attendance_check_within_geofence_is_none(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/attendance/check", headers=auth_headers,
                     json={"type": "in", "latitude": 10, "longitude": -66})
        assert r.status_code == 200
        d = r.json()
        # Field may be null or absent — both are acceptable per spec.
        assert d.get("within_geofence") is None, \
            f"Expected within_geofence=None (geofence removed) but got {d.get('within_geofence')}"
        # Coords should still be persisted for audit
        assert d.get("latitude") == 10
        assert d.get("longitude") == -66

    def test_attendance_check_without_coords(self, api, auth_headers):
        """type-only attendance should also work (geocerca removida)."""
        r = api.post(f"{BASE_URL}/api/attendance/check", headers=auth_headers,
                     json={"type": "out"})
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "out"
        assert d.get("within_geofence") is None


class TestSitesOptionalLatLng:
    """SiteIn now has optional latitude/longitude/radius_meters."""

    def test_create_site_without_lat_lng(self, api, auth_headers):
        rc = api.post(f"{BASE_URL}/api/sites", headers=auth_headers, json={
            "name": "TEST Sede NoGeo", "address": "Prueba sin coords"
        })
        assert rc.status_code == 200, f"Body: {rc.text}"
        d = rc.json()
        sid = d["site_id"]
        assert d["name"] == "TEST Sede NoGeo"
        assert d.get("latitude") is None
        assert d.get("longitude") is None
        assert d.get("radius_meters") is None

        # Verify it's persisted
        rl = api.get(f"{BASE_URL}/api/sites", headers=auth_headers)
        found = [s for s in rl.json() if s["site_id"] == sid]
        assert len(found) == 1
        assert found[0]["name"] == "TEST Sede NoGeo"

        # Update with only name/address
        ru = api.put(f"{BASE_URL}/api/sites/{sid}", headers=auth_headers, json={
            "name": "TEST Sede NoGeo 2", "address": "Nueva dir"
        })
        assert ru.status_code == 200
        assert ru.json()["name"] == "TEST Sede NoGeo 2"
        assert ru.json().get("address") == "Nueva dir"

        # Cleanup
        rd = api.delete(f"{BASE_URL}/api/sites/{sid}", headers=auth_headers)
        assert rd.status_code == 200

    def test_update_site_only_name(self, api, auth_headers):
        # Create then update with just name
        rc = api.post(f"{BASE_URL}/api/sites", headers=auth_headers, json={
            "name": "TEST Sede X"
        })
        assert rc.status_code == 200
        sid = rc.json()["site_id"]
        try:
            ru = api.put(f"{BASE_URL}/api/sites/{sid}", headers=auth_headers, json={
                "name": "TEST Sede X updated"
            })
            assert ru.status_code == 200
            assert ru.json()["name"] == "TEST Sede X updated"
        finally:
            api.delete(f"{BASE_URL}/api/sites/{sid}", headers=auth_headers)


class TestUsersPhotoEndpoint:
    """GET /api/users/{user_id}/photo returns selfie meta."""

    def test_photo_admin_self_not_onboarded(self, api, auth_headers):
        # Fetch admin's user_id via /auth/me
        me = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers).json()
        uid = me["user_id"]
        r = api.get(f"{BASE_URL}/api/users/{uid}/photo", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["user_id"] == uid
        assert "name" in d
        assert "onboarded" in d
        assert "selfie_base64" in d  # can be None if admin has no selfie

    def test_photo_onboarded_user(self, api, auth_headers):
        """Create a user, upload a selfie, then fetch photo."""
        email = f"TEST_photo_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST Photo", "role": "employee", "password": "pw12345"
        })
        assert rc.status_code == 200
        uid = rc.json()["user_id"]

        try:
            # Login as the new user and upload selfie
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "pw12345"})
            assert rl.status_code == 200
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                     "Content-Type": "application/json"}
            up = api.post(f"{BASE_URL}/api/onboarding/selfie", headers=emp_h,
                          json={"selfie_base64": "data:image/jpeg;base64,ZZZZ",
                                "face_descriptor": [0.1, 0.2, 0.3]})
            assert up.status_code == 200

            # Now fetch photo (admin)
            rp = api.get(f"{BASE_URL}/api/users/{uid}/photo", headers=auth_headers)
            assert rp.status_code == 200
            d = rp.json()
            assert d["user_id"] == uid
            assert d["name"] == "TEST Photo"
            assert d["onboarded"] is True
            assert d["selfie_base64"] == "data:image/jpeg;base64,ZZZZ"
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_photo_nonexistent_user_404(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/users/nonexistent_zzz_abc/photo", headers=auth_headers)
        assert r.status_code == 404

    def test_photo_requires_auth(self, api):
        r = requests.get(f"{BASE_URL}/api/users/whatever/photo")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Iteration 3 — Phase 4 UI-facing endpoints smoke tests
# ---------------------------------------------------------------------------
class TestPhase4Endpoints:
    """Quick regression for endpoints used by new Reports/Novelties/Team pages."""

    def test_reports_with_filters(self, api, auth_headers):
        r = api.get(
            f"{BASE_URL}/api/reports?from_date=2026-01-01&to_date=2026-12-31",
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_reports_without_filters(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/reports", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_reports_export_csv_content_disposition(self, api, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/reports/export", headers=h)
        assert r.status_code == 200
        # Should be attachment CSV
        cd = r.headers.get("content-disposition", "").lower()
        ct = r.headers.get("content-type", "").lower()
        assert ("attachment" in cd) or ("csv" in ct), \
            f"CSV export missing attachment/csv hint. CD={cd!r} CT={ct!r}"
        assert "record_id" in r.text
        assert "timestamp_utc" in r.text

    def test_novelties_list(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/novelties", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_novelty_vacation_future_bulk_approve_delete(self, api, auth_headers):
        # Create a vacation with future dates
        rc = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
            "type": "vacation",
            "start_date": "2027-01-05",
            "end_date": "2027-01-10",
            "reason": "TEST vacation iter3",
        })
        assert rc.status_code == 200
        d = rc.json()
        assert d["type"] == "vacation"
        assert d["status"] == "pending"
        nid = d["novelty_id"]

        # Bulk approve
        rd = api.post(f"{BASE_URL}/api/novelties/bulk-decide", headers=auth_headers,
                      json={"novelty_ids": [nid], "decision": "approved",
                            "comment": "TEST approve"})
        assert rd.status_code == 200
        assert rd.json()["updated"] == 1

        # Verify status persisted
        rl = api.get(f"{BASE_URL}/api/novelties", headers=auth_headers).json()
        found = [n for n in rl if n["novelty_id"] == nid]
        assert len(found) == 1
        assert found[0]["status"] == "approved"

        # Delete
        rdel = api.delete(f"{BASE_URL}/api/novelties/{nid}", headers=auth_headers)
        assert rdel.status_code == 200

    def test_novelties_bulk_decide_reject_multiple(self, api, auth_headers):
        # Create two pending novelties
        ids = []
        for i in range(2):
            rc = api.post(f"{BASE_URL}/api/novelties", headers=auth_headers, json={
                "type": "permission",
                "start_date": f"2027-02-0{i+1}",
                "end_date": f"2027-02-0{i+2}",
                "reason": f"TEST bulk {i}",
            })
            assert rc.status_code == 200
            ids.append(rc.json()["novelty_id"])

        rd = api.post(f"{BASE_URL}/api/novelties/bulk-decide", headers=auth_headers,
                      json={"novelty_ids": ids, "decision": "rejected"})
        assert rd.status_code == 200
        assert rd.json()["updated"] == 2

        # Cleanup
        for nid in ids:
            api.delete(f"{BASE_URL}/api/novelties/{nid}", headers=auth_headers)

    def test_attendance_team_days_7(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/attendance/team?days=7", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_employee_sidebar_role_restrictions_via_api(self, api, auth_headers):
        """Employee must NOT be able to fetch /reports or /attendance/team,
        but MUST be able to CRUD their own novelties."""
        email = f"TEST_p4emp_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST P4 Emp",
            "role": "employee", "password": "temp1234",
        })
        assert rc.status_code == 200
        uid = rc.json()["user_id"]

        try:
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "temp1234"})
            assert rl.status_code == 200
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                     "Content-Type": "application/json"}

            # Reports forbidden
            r1 = api.get(f"{BASE_URL}/api/reports", headers=emp_h)
            assert r1.status_code == 403
            # Team forbidden
            r2 = api.get(f"{BASE_URL}/api/attendance/team", headers=emp_h)
            assert r2.status_code == 403

            # Employee CAN create own novelty (no user_id needed)
            rc2 = api.post(f"{BASE_URL}/api/novelties", headers=emp_h, json={
                "type": "permission",
                "start_date": "2027-03-01",
                "end_date": "2027-03-02",
                "reason": "own",
            })
            assert rc2.status_code == 200
            own_nid = rc2.json()["novelty_id"]
            assert rc2.json()["user_id"] == uid

            # Employee can list (should see only own)
            rl2 = api.get(f"{BASE_URL}/api/novelties", headers=emp_h)
            assert rl2.status_code == 200
            for n in rl2.json():
                assert n["user_id"] == uid

            # Employee can delete own pending
            rdel = api.delete(f"{BASE_URL}/api/novelties/{own_nid}", headers=emp_h)
            assert rdel.status_code == 200
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)


# ---------------------------------------------------------------------------
# Iteration 4 — Executive Dashboard endpoint /api/stats/executive
# ---------------------------------------------------------------------------
class TestExecutiveStats:
    """GET /api/stats/executive?days=N — admin+supervisor only.
    Must return top_late (<=5) and department_ranking (<=8) with expected fields."""

    REQUIRED_TOP_FIELDS = {"user_id", "name", "cedula", "position",
                           "department_name", "late_count", "total_minutes"}
    REQUIRED_DEPT_FIELDS = {"department_name", "total_ins", "late", "late_pct"}

    def _assert_shape(self, d, days):
        assert d["days"] == days
        for k in ["since", "generated_at", "total_check_ins", "total_late",
                  "late_pct", "avg_late_minutes", "top_late", "department_ranking"]:
            assert k in d, f"missing key {k}"
        assert isinstance(d["top_late"], list)
        assert len(d["top_late"]) <= 5
        assert isinstance(d["department_ranking"], list)
        assert len(d["department_ranking"]) <= 8
        for item in d["top_late"]:
            missing = self.REQUIRED_TOP_FIELDS - set(item.keys())
            assert not missing, f"top_late item missing keys: {missing}"
        for item in d["department_ranking"]:
            missing = self.REQUIRED_DEPT_FIELDS - set(item.keys())
            assert not missing, f"department_ranking item missing keys: {missing}"

    def test_executive_default_30(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/stats/executive", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        self._assert_shape(d, 30)

    @pytest.mark.parametrize("days", [7, 14, 30, 60, 90])
    def test_executive_multiple_ranges(self, api, auth_headers, days):
        r = api.get(f"{BASE_URL}/api/stats/executive?days={days}", headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        self._assert_shape(d, days)
        assert isinstance(d["total_check_ins"], int)
        assert isinstance(d["total_late"], int)
        assert d["total_late"] <= d["total_check_ins"]

    def test_executive_employee_forbidden(self, api, auth_headers):
        email = f"TEST_execemp_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST Exec Emp",
            "role": "employee", "password": "pw12345"
        })
        assert rc.status_code == 200
        uid = rc.json()["user_id"]
        try:
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "pw12345"})
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}"}
            r = api.get(f"{BASE_URL}/api/stats/executive", headers=emp_h)
            assert r.status_code == 403
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)

    def test_executive_unauth(self, api):
        r = requests.get(f"{BASE_URL}/api/stats/executive")
        assert r.status_code == 401


class TestKioskRosterOnboarded:
    """Roster must include face_descriptor and selfie for onboarded users."""

    def test_kiosk_roster_shape(self, api, auth_headers):
        # Ensure at least one onboarded user exists
        email = f"TEST_roster_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=auth_headers, json={
            "email": email, "name": "TEST Roster", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "pw12345"})
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                     "Content-Type": "application/json"}
            api.post(f"{BASE_URL}/api/onboarding/selfie", headers=emp_h,
                     json={"selfie_base64": "data:image/jpeg;base64,QQQQ",
                           "face_descriptor": [0.5] * 128})

            r = api.get(f"{BASE_URL}/api/kiosk/roster")
            assert r.status_code == 200
            roster = r.json()
            assert isinstance(roster, list)
            found = [u for u in roster if u.get("user_id") == uid]
            assert len(found) == 1, "Onboarded user must appear in kiosk roster"
            u = found[0]
            # Required roster fields
            assert u.get("selfie_base64") == "data:image/jpeg;base64,QQQQ"
            assert u.get("face_descriptor") == [0.5] * 128
            assert u.get("name") == "TEST Roster"
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
