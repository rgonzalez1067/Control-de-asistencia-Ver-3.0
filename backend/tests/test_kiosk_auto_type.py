"""
Iteration 6 — Kiosk portrait + auto-detect entry/exit.

Tests:
  1. GET /api/kiosk/next-type/{user_id}: sin marcas hoy → 'in'
  2. POST /api/kiosk/attendance/check con type='auto' → responde type='in'
  3. GET /api/kiosk/next-type/{user_id} → 'out'
  4. POST /api/kiosk/attendance/check SIN type (default 'auto') → responde type='out'
  5. GET /api/kiosk/next-type/{user_id} → 'in'
  6. POST /api/kiosk/attendance/check con type='in' explícito → 'in' (backward compat)
  7. POST /api/kiosk/attendance/check con type='out' explícito → 'out'
  8. GET /api/kiosk/next-type/{nonexistent} → 404
  9. Cleanup mongo directamente (db.attendance.deleteMany)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://asistencia-web-1.preview.emergentagent.com").rstrip("/")
if "REACT_APP_BACKEND_URL" not in os.environ:
    p = "/app/frontend/.env"
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break

ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def test_user(admin_headers):
    email = f"TEST_kioskauto_{int(time.time())}@example.com"
    r = requests.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
        "email": email, "name": "TEST KioskAuto", "role": "employee", "password": "pw12345"
    })
    assert r.status_code == 200, r.text
    uid = r.json()["user_id"]
    yield uid, email
    # Cleanup attendance records via mongo (direct pymongo access)
    try:
        from pymongo import MongoClient
        mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mc[os.environ.get("DB_NAME", "test_database")]
        db.attendance.delete_many({"user_id": uid})
        mc.close()
    except Exception as e:
        print(f"Warning: could not cleanup attendance for {uid}: {e}")
    # Delete the user
    requests.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)


class TestKioskNextTypeAndAutoDetect:
    def test_01_next_type_no_marks_today_is_in(self, test_user):
        uid, _ = test_user
        # Ensure clean state first
        try:
            from pymongo import MongoClient
            mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = mc[os.environ.get("DB_NAME", "test_database")]
            db.attendance.delete_many({"user_id": uid})
            mc.close()
        except Exception:
            pass
        r = requests.get(f"{BASE_URL}/api/kiosk/next-type/{uid}")
        assert r.status_code == 200, r.text
        assert r.json() == {"next_type": "in"}

    def test_02_post_auto_creates_in(self, test_user):
        uid, _ = test_user
        r = requests.post(f"{BASE_URL}/api/kiosk/attendance/check",
                          json={"user_id": uid, "type": "auto"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "in", f"expected in, got {d.get('type')}"
        assert d["user_id"] == uid
        assert "record_id" in d

    def test_03_next_type_after_in_is_out(self, test_user):
        uid, _ = test_user
        r = requests.get(f"{BASE_URL}/api/kiosk/next-type/{uid}")
        assert r.status_code == 200, r.text
        assert r.json() == {"next_type": "out"}

    def test_04_post_no_type_defaults_auto_and_creates_out(self, test_user):
        uid, _ = test_user
        # NO type field at all -> should default to 'auto' -> resolve to 'out'
        r = requests.post(f"{BASE_URL}/api/kiosk/attendance/check",
                          json={"user_id": uid})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "out", f"expected out (auto after in), got {d.get('type')}"

    def test_05_next_type_after_out_is_in(self, test_user):
        uid, _ = test_user
        r = requests.get(f"{BASE_URL}/api/kiosk/next-type/{uid}")
        assert r.status_code == 200, r.text
        assert r.json() == {"next_type": "in"}

    def test_06_post_explicit_in_still_works(self, test_user):
        uid, _ = test_user
        r = requests.post(f"{BASE_URL}/api/kiosk/attendance/check",
                          json={"user_id": uid, "type": "in"})
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "in"

    def test_07_post_explicit_out_still_works(self, test_user):
        uid, _ = test_user
        r = requests.post(f"{BASE_URL}/api/kiosk/attendance/check",
                          json={"user_id": uid, "type": "out"})
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "out"

    def test_08_next_type_404_for_nonexistent(self):
        r = requests.get(f"{BASE_URL}/api/kiosk/next-type/nonexistent_zzz_xyz")
        assert r.status_code == 404


class TestKioskRegression:
    """Regression: existing kiosk endpoints still work as before."""

    def test_kiosk_unlock_admin(self):
        r = requests.post(f"{BASE_URL}/api/kiosk/unlock",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_kiosk_roster_shape(self):
        r = requests.get(f"{BASE_URL}/api/kiosk/roster")
        assert r.status_code == 200
        roster = r.json()
        assert isinstance(roster, list)
        # At least the onboarded users should carry selfie_base64 / face_descriptor keys
        onboarded = [u for u in roster if u.get("selfie_base64") or u.get("face_descriptor")]
        # Not strictly required at least one, but let's just check the fields exist in shape
        for u in roster:
            assert "user_id" in u
            assert "name" in u

    def test_kiosk_verify_pin_no_pin_configured_returns_404(self, admin_headers):
        # Pick any real user without pin (fresh temporary)
        email = f"TEST_pinreg_{int(time.time())}@example.com"
        rc = requests.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST NoPin", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            r = requests.post(f"{BASE_URL}/api/kiosk/verify-pin",
                              json={"user_id": uid, "pin": "1234"})
            assert r.status_code == 404
        finally:
            requests.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_kiosk_verify_pin_success_and_wrong(self, admin_headers):
        # Create a fresh employee, set PIN, verify success + wrong
        email = f"TEST_pinok_{int(time.time())}@example.com"
        rc = requests.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST PinOK", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            # Admin sets PIN
            rp = requests.post(f"{BASE_URL}/api/users/{uid}/pin",
                               headers=admin_headers, json={"pin": "4321"})
            assert rp.status_code == 200, rp.text
            # Verify success
            r_ok = requests.post(f"{BASE_URL}/api/kiosk/verify-pin",
                                 json={"user_id": uid, "pin": "4321"})
            assert r_ok.status_code == 200
            assert r_ok.json() == {"ok": True}
            # Verify wrong
            r_bad = requests.post(f"{BASE_URL}/api/kiosk/verify-pin",
                                  json={"user_id": uid, "pin": "9999"})
            assert r_bad.status_code == 401
        finally:
            requests.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)
