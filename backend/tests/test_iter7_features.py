"""
Iteration 7 — Backend tests for new features:
 (1) POST /api/users acepta pin opcional (4-8 dígitos).
 (2) POST /api/users/{id}/pin — admin y self; employee cambiando otro → 403.
 (3) POST /api/users/{id}/selfie — admin puede a otro; employee a otro → 403.
 (4) POST /api/kiosk/reenroll-face — FormData; PIN correcto→200, incorrecto→401.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://asistencia-web-1.preview.emergentagent.com",
).rstrip("/")

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


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_headers(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# (1) POST /api/users with optional 'pin'
# ---------------------------------------------------------------------------
class TestUsersCreateWithPin:

    def test_create_user_with_valid_pin(self, api, admin_headers):
        email = f"TEST_pin_ok_{int(time.time())}@example.com"
        r = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Pin OK",
            "role": "employee", "password": "pw12345", "pin": "1234"
        })
        assert r.status_code == 200, r.text
        uid = r.json()["user_id"]
        # sanitized response must not expose pin_code_hash
        assert "pin_code_hash" not in r.json()
        assert "pin" not in r.json()
        try:
            # Verify pin works via public endpoint
            vp = api.post(f"{BASE_URL}/api/kiosk/verify-pin",
                          json={"user_id": uid, "pin": "1234"})
            assert vp.status_code == 200, f"verify-pin failed: {vp.status_code} {vp.text}"
            assert vp.json() == {"ok": True}
            # Wrong pin -> 401
            vpw = api.post(f"{BASE_URL}/api/kiosk/verify-pin",
                           json={"user_id": uid, "pin": "9999"})
            assert vpw.status_code == 401
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_create_user_with_pin_non_numeric_400(self, api, admin_headers):
        email = f"TEST_pin_bad_{int(time.time())}@example.com"
        r = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Pin Bad",
            "role": "employee", "password": "pw12345", "pin": "abcd"
        })
        assert r.status_code == 400
        assert "PIN" in r.text or "pin" in r.text.lower()

    def test_create_user_with_pin_too_short_400(self, api, admin_headers):
        email = f"TEST_pin_short_{int(time.time())}@example.com"
        r = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Pin Short",
            "role": "employee", "password": "pw12345", "pin": "12"
        })
        assert r.status_code == 400

    def test_create_user_with_pin_too_long_400(self, api, admin_headers):
        email = f"TEST_pin_long_{int(time.time())}@example.com"
        r = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Pin Long",
            "role": "employee", "password": "pw12345", "pin": "123456789"
        })
        assert r.status_code == 400

    def test_create_user_without_pin_verify_returns_404(self, api, admin_headers):
        email = f"TEST_no_pin_{int(time.time())}@example.com"
        r = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST No Pin",
            "role": "employee", "password": "pw12345"
        })
        assert r.status_code == 200
        uid = r.json()["user_id"]
        try:
            vp = api.post(f"{BASE_URL}/api/kiosk/verify-pin",
                          json={"user_id": uid, "pin": "1234"})
            # user exists but pin_code_hash NOT set → 404 "Usuario o PIN no configurado"
            assert vp.status_code == 404
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)


# ---------------------------------------------------------------------------
# (2) POST /api/users/{id}/pin — admin & self
# ---------------------------------------------------------------------------
class TestSetPinPermissions:

    def test_admin_sets_pin_for_other_user(self, api, admin_headers):
        email = f"TEST_setpin_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST",
            "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            r = api.post(f"{BASE_URL}/api/users/{uid}/pin",
                         headers=admin_headers, json={"pin": "4321"})
            assert r.status_code == 200
            assert r.json() == {"ok": True}

            # Verify via public endpoint
            vp = api.post(f"{BASE_URL}/api/kiosk/verify-pin",
                          json={"user_id": uid, "pin": "4321"})
            assert vp.status_code == 200
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_employee_can_set_own_pin(self, api, admin_headers):
        email = f"TEST_selfpin_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Self",
            "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": "pw12345"})
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                     "Content-Type": "application/json"}
            r = api.post(f"{BASE_URL}/api/users/{uid}/pin",
                         headers=emp_h, json={"pin": "5678"})
            assert r.status_code == 200

            # Verify pin works
            vp = api.post(f"{BASE_URL}/api/kiosk/verify-pin",
                          json={"user_id": uid, "pin": "5678"})
            assert vp.status_code == 200
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_employee_cannot_set_other_pin_403(self, api, admin_headers):
        # Create two employees
        e1 = f"TEST_a_{int(time.time())}@example.com"
        e2 = f"TEST_b_{int(time.time())}@example.com"
        r1 = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": e1, "name": "A", "role": "employee", "password": "pw12345"
        })
        r2 = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": e2, "name": "B", "role": "employee", "password": "pw12345"
        })
        uid1 = r1.json()["user_id"]
        uid2 = r2.json()["user_id"]
        try:
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": e1, "password": "pw12345"})
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                     "Content-Type": "application/json"}
            r = api.post(f"{BASE_URL}/api/users/{uid2}/pin",
                         headers=emp_h, json={"pin": "1111"})
            assert r.status_code == 403
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid1}", headers=admin_headers)
            api.delete(f"{BASE_URL}/api/users/{uid2}", headers=admin_headers)

    def test_set_pin_invalid_format_400(self, api, admin_headers):
        email = f"TEST_pinfmt_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            r = api.post(f"{BASE_URL}/api/users/{uid}/pin",
                         headers=admin_headers, json={"pin": "ab"})
            assert r.status_code == 400
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)


# ---------------------------------------------------------------------------
# (3) POST /api/users/{id}/selfie — admin/self perms
# ---------------------------------------------------------------------------
class TestSelfiePermissions:

    def test_admin_sets_selfie_for_other_user_marks_onboarded(self, api, admin_headers):
        email = f"TEST_selfie_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Selfie",
            "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            # Before: onboarded false
            rg = api.get(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)
            assert rg.json().get("onboarded") is False

            r = api.post(f"{BASE_URL}/api/users/{uid}/selfie",
                         headers=admin_headers,
                         json={"selfie_base64": "data:image/jpeg;base64,AAAA",
                               "face_descriptor": [0.1, 0.2]})
            assert r.status_code == 200
            assert r.json() == {"ok": True}

            # onboarded true
            rg2 = api.get(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)
            assert rg2.json().get("onboarded") is True

            # photo endpoint returns the base64
            rp = api.get(f"{BASE_URL}/api/users/{uid}/photo", headers=admin_headers)
            assert rp.status_code == 200
            assert rp.json()["selfie_base64"] == "data:image/jpeg;base64,AAAA"
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_employee_cannot_set_other_selfie_403(self, api, admin_headers):
        e1 = f"TEST_sa_{int(time.time())}@example.com"
        e2 = f"TEST_sb_{int(time.time())}@example.com"
        r1 = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": e1, "name": "A", "role": "employee", "password": "pw12345"
        })
        r2 = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": e2, "name": "B", "role": "employee", "password": "pw12345"
        })
        uid1 = r1.json()["user_id"]
        uid2 = r2.json()["user_id"]
        try:
            rl = api.post(f"{BASE_URL}/api/auth/login",
                          json={"email": e1, "password": "pw12345"})
            emp_h = {"Authorization": f"Bearer {rl.json()['token']}",
                     "Content-Type": "application/json"}
            r = api.post(f"{BASE_URL}/api/users/{uid2}/selfie",
                         headers=emp_h,
                         json={"selfie_base64": "data:image/jpeg;base64,XYZ"})
            assert r.status_code == 403
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid1}", headers=admin_headers)
            api.delete(f"{BASE_URL}/api/users/{uid2}", headers=admin_headers)


# ---------------------------------------------------------------------------
# (4) POST /api/kiosk/reenroll-face (FormData)
# ---------------------------------------------------------------------------
class TestKioskReenrollFace:

    def test_reenroll_correct_pin_updates_selfie(self, api, admin_headers):
        email = f"TEST_reen_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Reenroll",
            "role": "employee", "password": "pw12345", "pin": "2468"
        })
        uid = rc.json()["user_id"]
        try:
            # POST as FormData (not JSON). No auth required.
            r = requests.post(
                f"{BASE_URL}/api/kiosk/reenroll-face",
                data={
                    "user_id": uid,
                    "pin": "2468",
                    "selfie_base64": "data:image/jpeg;base64,NEWSELFIE",
                    "face_descriptor": "[0.9, 0.1]",
                },
            )
            assert r.status_code == 200, r.text
            assert r.json() == {"ok": True}

            # Verify selfie updated + onboarded
            rp = api.get(f"{BASE_URL}/api/users/{uid}/photo", headers=admin_headers)
            assert rp.status_code == 200
            assert rp.json()["selfie_base64"] == "data:image/jpeg;base64,NEWSELFIE"
            assert rp.json()["onboarded"] is True
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_reenroll_wrong_pin_401(self, api, admin_headers):
        email = f"TEST_reen_bad_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST Reenroll Bad",
            "role": "employee", "password": "pw12345", "pin": "1357"
        })
        uid = rc.json()["user_id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/kiosk/reenroll-face",
                data={
                    "user_id": uid,
                    "pin": "9999",
                    "selfie_base64": "data:image/jpeg;base64,SHOULD_NOT_SAVE",
                },
            )
            assert r.status_code == 401
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)

    def test_reenroll_user_without_pin_401(self, api, admin_headers):
        """User exists but has no pin_code_hash configured."""
        email = f"TEST_reen_nopin_{int(time.time())}@example.com"
        rc = api.post(f"{BASE_URL}/api/users", headers=admin_headers, json={
            "email": email, "name": "TEST No Pin", "role": "employee", "password": "pw12345"
        })
        uid = rc.json()["user_id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/kiosk/reenroll-face",
                data={"user_id": uid, "pin": "1234", "selfie_base64": "data:image/jpeg;base64,X"},
            )
            assert r.status_code == 401
        finally:
            api.delete(f"{BASE_URL}/api/users/{uid}", headers=admin_headers)
