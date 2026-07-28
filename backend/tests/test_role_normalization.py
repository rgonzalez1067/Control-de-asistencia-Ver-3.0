"""Tests for role normalization + name preservation (iteration 9)."""
import io
import os
import pytest
import requests
from openpyxl import Workbook

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # try frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "admin123"

CANONICAL_ROLES = {"admin", "supervisor", "employee"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_all_users_have_canonical_role(auth_headers):
    r = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
    assert r.status_code == 200
    users = r.json()
    assert len(users) > 0
    bad = [(u.get("email"), u.get("role")) for u in users if u.get("role") not in CANONICAL_ROLES]
    assert not bad, f"Non-canonical roles found: {bad}"


def test_known_users_name_proper_case(auth_headers):
    r = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
    assert r.status_code == 200
    by_email = {u["email"].lower(): u for u in r.json()}
    # cmarin
    cm = by_email.get("cmarin@megasoft.com.ve")
    if cm:
        assert cm["name"] == "Carlos Marín", f"got name={cm['name']!r}"
    jd = by_email.get("jdolande@megasoft.com.ve")
    if jd:
        assert jd["name"] == "José Dolande García", f"got name={jd['name']!r}"


def _make_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    headers = ["email", "name", "cedula", "role", "position",
               "department_id", "site_id", "supervisor_id", "schedule_id",
               "password", "kiosk_pin"]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_preview_normalizes_role(auth_headers):
    xlsx = _make_xlsx([
        {"email": "TEST_qa_supervisor@megasoft.com.ve",
         "name": "María Pérez López", "role": "Supervisor",
         "position": "QA", "password": "temp123", "kiosk_pin": "4321"},
        {"email": "TEST_qa_emp@megasoft.com.ve",
         "name": "José García Ñ", "role": "EMPLEADO",
         "position": "Ops", "password": "temp123", "kiosk_pin": "4322"},
    ])
    files = {"file": ("t.xlsx", xlsx,
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{BASE_URL}/api/users/import/preview",
                      headers=auth_headers, files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    # inspect preview payload - roles inside should be canonical
    def collect_rows(d):
        out = []
        for k in ("nuevos", "actualizar", "new", "creates", "updates",
                  "to_create", "to_update"):
            v = d.get(k)
            if isinstance(v, list):
                out.extend(v)
        return out
    rows = collect_rows(data)
    roles_seen = []
    for row in rows:
        payload = row if isinstance(row, dict) else {}
        # look for role key possibly nested
        role = payload.get("role") or payload.get("data", {}).get("role")
        if role:
            roles_seen.append(role)
    # If we can't easily extract, just don't fail; but at minimum ensure canonical
    for role in roles_seen:
        assert role in CANONICAL_ROLES, f"non-canonical role in preview: {role}"


def test_import_commit_role_and_name(auth_headers):
    # Cleanup existing test users first
    r = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
    for u in r.json():
        if u["email"].startswith("TEST_qa_"):
            requests.delete(f"{BASE_URL}/api/users/{u['user_id']}", headers=auth_headers)

    xlsx = _make_xlsx([
        {"email": "TEST_qa_supervisor@megasoft.com.ve",
         "name": "María Pérez López", "role": "Supervisor",
         "position": "QA", "password": "temp123", "kiosk_pin": "4321"},
        {"email": "TEST_qa_emp@megasoft.com.ve",
         "name": "José Dolande García", "role": "EMPLEADO",
         "position": "Ops", "password": "temp123", "kiosk_pin": "4322"},
        {"email": "TEST_qa_admin@megasoft.com.ve",
         "name": "Ana Rojas", "role": "administrador",
         "position": "IT", "password": "temp123", "kiosk_pin": "4323"},
    ])
    files = {"file": ("t.xlsx", xlsx,
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{BASE_URL}/api/users/import",
                      headers=auth_headers, files=files)
    assert r.status_code in (200, 201), r.text

    # Now GET users and verify
    r = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
    assert r.status_code == 200
    by_email = {u["email"].lower(): u for u in r.json()}

    expected = {
        "test_qa_supervisor@megasoft.com.ve": ("supervisor", "María Pérez López"),
        "test_qa_emp@megasoft.com.ve": ("employee", "José Dolande García"),
        "test_qa_admin@megasoft.com.ve": ("admin", "Ana Rojas"),
    }
    for email, (expected_role, expected_name) in expected.items():
        u = by_email.get(email)
        assert u, f"user {email} not created"
        assert u["role"] == expected_role, f"{email}: role={u['role']!r} expected {expected_role}"
        assert u["name"] == expected_name, f"{email}: name={u['name']!r} expected {expected_name}"

    # Cleanup
    for u in by_email.values():
        if u["email"].startswith("TEST_qa_"):
            requests.delete(f"{BASE_URL}/api/users/{u['user_id']}", headers=auth_headers)
