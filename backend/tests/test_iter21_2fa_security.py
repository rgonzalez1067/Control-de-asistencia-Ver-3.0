"""Tests iteración 21 — Módulo Seguridad global + 2FA por correo."""
import os
import time
import hashlib
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

ADMIN = ("rgonzalez@megasoft.com.ve", "Sol*1401*1010")
KIOSK = ("kiosco.tbp@megasoft.com.ve", "Mega2026*")
EMPLOYEE = ("jgil@megasoft.com.ve", "NewJgil!234")


# ---------------- helpers ----------------
def _mongo():
    with open("/app/backend/.env") as f:
        env = {ln.split("=", 1)[0]: ln.split("=", 1)[1].strip().strip('"')
               for ln in f if "=" in ln and not ln.startswith("#")}
    url = os.environ.get("MONGO_URL") or env.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or env.get("DB_NAME")
    return MongoClient(url)[db_name]


@pytest.fixture(scope="module")
def db():
    return _mongo()


@pytest.fixture(scope="module")
def admin_token():
    # Asegura 2FA off antes de intentar login admin
    r = _login(ADMIN[0], ADMIN[1])
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("requires_otp"):
        # Necesitamos apagar 2FA — usar directamente Mongo
        db = _mongo()
        db.settings.update_one({"_id": "security"},
                               {"$set": {"enable_email_2fa": False}}, upsert=True)
        r = _login(ADMIN[0], ADMIN[1])
        body = r.json()
    return body["token"]


@pytest.fixture(autouse=True)
def _disable_2fa_between_tests(db):
    yield
    # cleanup por seguridad
    db.settings.update_one({"_id": "security"},
                           {"$set": {"enable_email_2fa": False}}, upsert=True)


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


_LAST_LOGIN_TS = [0.0]


def _login(email, password):
    """Login espaciado para evitar rate limit 5/min."""
    global _LAST_LOGIN_TS
    now = time.time()
    # Mantener ~1 request cada 13s → 4.6/min
    wait = 13 - (now - _LAST_LOGIN_TS[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_LOGIN_TS[0] = time.time()
    return requests.post(f"{BASE_URL}/api/auth/login",
                         json={"email": email, "password": password})


def _brute_force_otp(otp_hash: str) -> str:
    for i in range(1_000_000):
        code = f"{i:06d}"
        if hashlib.sha256(code.encode()).hexdigest() == otp_hash:
            return code
    return ""


def _fetch_latest_otp(db, user_email):
    doc = db.otp_challenges.find_one({"email": user_email}, sort=[("created_at", -1)])
    return doc


# ============ Security settings endpoints ============
class TestSecuritySettings:
    def test_get_requires_admin(self):
        r = requests.get(f"{BASE_URL}/api/security-settings")
        assert r.status_code in (401, 403)

    def test_get_returns_config_defaults_bounds(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/security-settings",
                         headers=_auth(admin_token))
        assert r.status_code == 200, r.text
        b = r.json()
        assert "config" in b and "defaults" in b and "bounds" in b
        assert "max_login_attempts" in b["config"]
        assert "enable_email_2fa" in b["config"]
        assert b["bounds"]["max_login_attempts"]["min"] == 3

    def test_put_rejects_out_of_range(self, admin_token):
        r = requests.put(f"{BASE_URL}/api/security-settings",
                         headers=_auth(admin_token),
                         json={"max_login_attempts": 999})
        assert r.status_code == 400

    def test_put_rejects_warning_ge_expiration(self, admin_token):
        r = requests.put(f"{BASE_URL}/api/security-settings",
                         headers=_auth(admin_token),
                         json={"password_expiration_days": 30,
                               "password_expiration_warning_days": 30})
        assert r.status_code == 400

    def test_put_accepts_valid(self, admin_token):
        r = requests.put(f"{BASE_URL}/api/security-settings",
                         headers=_auth(admin_token),
                         json={"max_login_attempts": 6, "lockout_minutes": 15})
        assert r.status_code == 200, r.text
        assert r.json()["config"]["max_login_attempts"] == 6

    def test_public_security_policy(self):
        r = requests.get(f"{BASE_URL}/api/public/security-policy")
        assert r.status_code == 200
        b = r.json()
        assert "enable_email_2fa" in b
        assert "login_max_failed" in b
        assert "password_max_age_days" in b


# ============ Login flow (2FA off) ============
class TestLogin2FAOff:
    def test_login_direct_jwt(self, db):
        db.settings.update_one({"_id": "security"},
                               {"$set": {"enable_email_2fa": False}}, upsert=True)
        r = _login(ADMIN[0], ADMIN[1])
        assert r.status_code == 200
        b = r.json()
        assert "token" in b and "user" in b
        assert not b.get("requires_otp")


# ============ 2FA on ============
class TestLogin2FAOn:
    def test_login_returns_otp_challenge(self, admin_token, db):
        r = requests.put(f"{BASE_URL}/api/security-settings",
                         headers=_auth(admin_token),
                         json={"enable_email_2fa": True})
        assert r.status_code == 200
        # Login employee
        r = _login(ADMIN[0], ADMIN[1])
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("requires_otp") is True
        assert "otp_token" in b
        assert "email_masked" in b and "*" in b["email_masked"]
        assert "expires_in_minutes" in b
        assert "delivery" in b
        assert "token" not in b or b.get("token") is None
        # Verifica registro en Mongo
        time.sleep(0.3)
        doc = _fetch_latest_otp(db, ADMIN[0])
        assert doc is not None
        assert doc["attempts"] == 0
        assert doc.get("consumed_at") is None

    def test_verify_otp_wrong_code_decrements_attempts(self, admin_token, db):
        db.settings.update_one({"_id": "security"},
                               {"$set": {"enable_email_2fa": True,
                                         "otp_max_attempts": 3}}, upsert=True)
        r = _login(ADMIN[0], ADMIN[1])
        otp_token = r.json()["otp_token"]
        # 3 intentos incorrectos → lockout
        for i in range(3):
            r = requests.post(f"{BASE_URL}/api/auth/verify-otp",
                              json={"otp_token": otp_token, "code": "111111"})
            assert r.status_code == 401
        # nuevo intento con código correcto no debería funcionar (consumed)
        doc = _fetch_latest_otp(db, ADMIN[0])
        assert doc.get("consumed_at") is not None
        assert doc.get("invalidated_reason") == "max_attempts"

    def test_verify_otp_correct_code_success(self, admin_token, db):
        db.settings.update_one({"_id": "security"},
                               {"$set": {"enable_email_2fa": True,
                                         "otp_max_attempts": 3,
                                         "otp_expiration_minutes": 5}}, upsert=True)
        r = _login(ADMIN[0], ADMIN[1])
        otp_token = r.json()["otp_token"]
        doc = _fetch_latest_otp(db, ADMIN[0])
        code = _brute_force_otp(doc["otp_hash"])
        assert code, "brute force failed"
        r = requests.post(f"{BASE_URL}/api/auth/verify-otp",
                          json={"otp_token": otp_token, "code": code})
        assert r.status_code == 200, r.text
        b = r.json()
        assert "token" in b and "user" in b
        assert "must_change_password" in b
        # Reto consumido
        doc2 = db.otp_challenges.find_one({"challenge_id": doc["challenge_id"]})
        assert doc2["consumed_at"] is not None

    def test_verify_otp_reuse_rejected(self, admin_token, db):
        db.settings.update_one({"_id": "security"},
                               {"$set": {"enable_email_2fa": True}}, upsert=True)
        r = _login(ADMIN[0], ADMIN[1])
        otp_token = r.json()["otp_token"]
        doc = _fetch_latest_otp(db, ADMIN[0])
        code = _brute_force_otp(doc["otp_hash"])
        r1 = requests.post(f"{BASE_URL}/api/auth/verify-otp",
                           json={"otp_token": otp_token, "code": code})
        assert r1.status_code == 200
        r2 = requests.post(f"{BASE_URL}/api/auth/verify-otp",
                           json={"otp_token": otp_token, "code": code})
        assert r2.status_code == 401

    def test_verify_otp_invalid_token(self):
        r = requests.post(f"{BASE_URL}/api/auth/verify-otp",
                          json={"otp_token": "not-a-jwt", "code": "123456"})
        assert r.status_code == 401

    def test_kiosk_bypass_2fa(self, admin_token, db):
        db.settings.update_one({"_id": "security"},
                               {"$set": {"enable_email_2fa": True}}, upsert=True)
        r = _login(KIOSK[0], KIOSK[1])
        assert r.status_code == 200, r.text
        b = r.json()
        assert "token" in b and b["token"]
        assert not b.get("requires_otp")


# ============ Dynamic lockout ============
class TestDynamicLockout:
    def test_max_attempts_dynamic(self, admin_token, db):
        # Set attempts=3, lockout=1 minute
        r = requests.put(f"{BASE_URL}/api/security-settings",
                         headers=_auth(admin_token),
                         json={"max_login_attempts": 3, "lockout_minutes": 1,
                               "enable_email_2fa": False})
        assert r.status_code == 200
        # Test user con contraseña equivocada — 3 intentos → 423
        # Uso una cuenta test dedicada para no bloquear a jgil
        db.users.update_one({"email": ADMIN[0]},
                            {"$set": {"failed_login_attempts": 0, "locked_until": None}})
        for i in range(3):
            r = _login(EMPLOYEE[0], "wrongpass")
        # El tercer intento fallido dispara lockout
        assert r.status_code == 423, r.text
        # Restablece
        db.users.update_one({"email": ADMIN[0]},
                            {"$set": {"failed_login_attempts": 0, "locked_until": None}})
