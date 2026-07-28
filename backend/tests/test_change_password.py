"""Tests for POST /api/auth/change-password.

CRITICAL: Restores admin password to 'admin123' after successful change to keep env usable.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:3000"
# Fallback: read from frontend/.env if not in env
if "localhost" in BASE_URL or not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PW = "admin123"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    return r


@pytest.fixture(scope="module")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PW)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


class TestChangePasswordAuth:
    def test_no_token_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          json={"old_password": "x", "new_password": "yyyyyyyy"}, timeout=15)
        assert r.status_code == 401

    def test_invalid_token_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          headers={"Authorization": "Bearer invalid.token.here"},
                          json={"old_password": "x", "new_password": "yyyyyyyy"}, timeout=15)
        assert r.status_code == 401


class TestChangePasswordValidation:
    def test_wrong_current_password_returns_400(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          headers=_headers(admin_token),
                          json={"old_password": "wrongpw!!!", "new_password": "NuevaTest2026!"},
                          timeout=15)
        assert r.status_code == 400
        assert "Contraseña actual incorrecta" in r.json().get("detail", "")

    def test_new_password_too_short_returns_422(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          headers=_headers(admin_token),
                          json={"old_password": ADMIN_PW, "new_password": "short"},
                          timeout=15)
        assert r.status_code == 422
        body = r.json()
        # Pydantic v2 error format
        errs = body.get("detail", [])
        assert any("string_too_short" in str(e.get("type", "")) or "at least 8" in str(e).lower()
                   for e in (errs if isinstance(errs, list) else [errs]))

    def test_new_equal_to_old_returns_400(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          headers=_headers(admin_token),
                          json={"old_password": ADMIN_PW, "new_password": ADMIN_PW},
                          timeout=15)
        # admin123 is only 8 chars, so it passes min_length. Should hit distinct-check.
        assert r.status_code == 400
        assert "distinta" in r.json().get("detail", "").lower()


class TestChangePasswordSuccessFlow:
    """End-to-end: change → login with new → restore → login with original."""

    NEW_PW = "NuevaTest2026!"

    def test_full_change_and_restore(self, admin_token):
        # 1. Change admin123 -> NEW_PW
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          headers=_headers(admin_token),
                          json={"old_password": ADMIN_PW, "new_password": self.NEW_PW},
                          timeout=15)
        assert r.status_code == 200, f"Change failed: {r.text}"
        assert r.json() == {"ok": True}

        # 2. Old password no longer works
        r_old = _login(ADMIN_EMAIL, ADMIN_PW)
        assert r_old.status_code == 401, "Old password should NOT authenticate anymore"

        # 3. New password works
        r_new = _login(ADMIN_EMAIL, self.NEW_PW)
        assert r_new.status_code == 200, f"New password login failed: {r_new.text}"
        new_token = r_new.json()["token"]

        # 4. RESTORE to admin123 (critical for env usability)
        r_restore = requests.post(f"{BASE_URL}/api/auth/change-password",
                                  headers=_headers(new_token),
                                  json={"old_password": self.NEW_PW, "new_password": ADMIN_PW},
                                  timeout=15)
        assert r_restore.status_code == 200, f"RESTORE FAILED: {r_restore.text}"

        # 5. Verify admin123 works again
        r_final = _login(ADMIN_EMAIL, ADMIN_PW)
        assert r_final.status_code == 200, "CRITICAL: admin123 does not authenticate after restore!"
