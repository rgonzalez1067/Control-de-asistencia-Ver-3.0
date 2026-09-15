"""Iteración 19 — Persistencia TRANSACCIONAL de planificaciones.

Verifica:
  1. POST plan con `assignments` inline → 1 request crea plan + reemplaza asignaciones.
  2. Rechazo por solape (409 plan_range_overlap) NO escribe nada: plan original intacto.
  3. Overwrite=true reemplaza el plan solapado.
  4. PUT plan con `assignments` reemplaza EXACTO en el rango (celda quitada no reaparece).
  5. Regresión: bulk (cells) y clear (cells) legacy siguen funcionando.
  6. Regresión: matriz especial GET /reports/matrix?schedule_id=__special refleja assignments.
"""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for ln in env_path.read_text().splitlines():
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL no configurado")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "rgonzalez@megasoft.com.ve"
ADMIN_PASSWORD = "Sol*1401*1010"

FROM_A = "2027-03-01"
TO_A = "2027-03-10"
FROM_B = "2027-03-05"
TO_B = "2027-03-15"

PLAN_A_NAME = "ZZ Plan A iter19"
PLAN_B_NAME = "ZZ Plan B iter19"
PLAN_TX_NAME = "ZZ Tx Test iter19"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"Login admin falló: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def eligible_users(client):
    r = client.get(f"{BASE_URL}/api/schedule-assignments/eligible-users", timeout=15)
    assert r.status_code == 200, r.text
    users = r.json()
    assert len(users) >= 2, "Se requieren al menos 2 empleados elegibles"
    return users[:2]


@pytest.fixture(scope="module")
def a_schedule(client):
    r = client.get(f"{BASE_URL}/api/schedules", timeout=15)
    assert r.status_code == 200
    scs = r.json()
    assert len(scs) >= 1
    return scs[0]


@pytest.fixture(scope="module", autouse=True)
def cleanup(client, eligible_users):
    yield
    # Delete plans by name
    r = client.get(f"{BASE_URL}/api/schedule-assignment-plans", timeout=15)
    if r.status_code == 200:
        for p in r.json():
            if p.get("name") in {PLAN_A_NAME, PLAN_B_NAME, PLAN_TX_NAME}:
                client.delete(f"{BASE_URL}/api/schedule-assignment-plans/{p['plan_id']}", timeout=15)
    # Wipe assignments for test users in march 2027
    uids = [u["user_id"] for u in eligible_users]
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": uids,
                      "dates": [f"2027-03-{d:02d}" for d in range(1, 32)]},
                timeout=30)


def _get_assignments(client, uids, f, t):
    r = client.get(f"{BASE_URL}/api/schedule-assignments",
                   params={"from_date": f, "to_date": t, "user_ids": ",".join(uids)},
                   timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 1) Plan transaccional (post con assignments) ----------
def test_1_transactional_create_plan(client, eligible_users, a_schedule):
    u1, u2 = eligible_users
    body = {
        "name": PLAN_TX_NAME,
        "from_date": FROM_A,
        "to_date": TO_A,
        "user_ids": [u1["user_id"], u2["user_id"]],
        "row_order": [u1["user_id"], u2["user_id"]],
        "assignments": [
            {"user_id": u1["user_id"], "date": "2027-03-02",
             "kind": "shift", "schedule_id": a_schedule["schedule_id"]},
            {"user_id": u2["user_id"], "date": "2027-03-04",
             "kind": "novelty", "novelty_type": "remote"},
        ],
    }
    r = client.post(f"{BASE_URL}/api/schedule-assignment-plans", json=body, timeout=15)
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["name"] == PLAN_TX_NAME
    # Verify persisted
    asgs = _get_assignments(client, [u1["user_id"], u2["user_id"]], FROM_A, TO_A)
    assert len(asgs) == 2
    pairs = {(a["user_id"], a["date"]) for a in asgs}
    assert (u1["user_id"], "2027-03-02") in pairs
    assert (u2["user_id"], "2027-03-04") in pairs
    # Cleanup this plan
    client.delete(f"{BASE_URL}/api/schedule-assignment-plans/{plan['plan_id']}", timeout=15)
    # And clear these cells so next tests start clean
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"cells": [{"user_id": u1["user_id"], "date": "2027-03-02"},
                                {"user_id": u2["user_id"], "date": "2027-03-04"}]},
                timeout=15)


# ---------- 2) Rechazo por solape NO modifica original ----------
def test_2_overlap_rejects_and_leaves_original_intact(client, eligible_users, a_schedule):
    u1 = eligible_users[0]
    # Create Plan A with one assignment
    r = client.post(f"{BASE_URL}/api/schedule-assignment-plans", json={
        "name": PLAN_A_NAME, "from_date": FROM_A, "to_date": TO_A,
        "user_ids": [u1["user_id"]], "row_order": [u1["user_id"]],
        "assignments": [{"user_id": u1["user_id"], "date": "2027-03-03",
                         "kind": "shift", "schedule_id": a_schedule["schedule_id"]}],
    }, timeout=15)
    assert r.status_code == 200, r.text
    plan_a = r.json()

    # Snapshot
    before = _get_assignments(client, [u1["user_id"]], FROM_A, TO_A)
    assert len(before) == 1
    assert before[0]["date"] == "2027-03-03"
    assert before[0]["kind"] == "shift"

    # Try Plan B (overlapping, same user, DIFFERENT assignment on same date)
    r2 = client.post(f"{BASE_URL}/api/schedule-assignment-plans", json={
        "name": PLAN_B_NAME, "from_date": FROM_B, "to_date": TO_B,
        "user_ids": [u1["user_id"]], "row_order": [u1["user_id"]],
        "assignments": [{"user_id": u1["user_id"], "date": "2027-03-03",
                         "kind": "novelty", "novelty_type": "vacation"}],
    }, timeout=15)
    assert r2.status_code == 409, r2.text
    detail = r2.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "plan_range_overlap"

    # Confirm original NOT modified
    after = _get_assignments(client, [u1["user_id"]], FROM_A, TO_A)
    assert len(after) == 1
    assert after[0]["date"] == "2027-03-03"
    assert after[0]["kind"] == "shift"
    assert after[0]["schedule_id"] == a_schedule["schedule_id"]

    # Plan A still exists
    r3 = client.get(f"{BASE_URL}/api/schedule-assignment-plans", timeout=15)
    plan_ids = {p["plan_id"] for p in r3.json()}
    assert plan_a["plan_id"] in plan_ids


# ---------- 3) Overwrite=true reemplaza plan A ----------
def test_3_overwrite_replaces(client, eligible_users, a_schedule):
    u1 = eligible_users[0]
    # Plan A must exist from previous test
    r_before = client.get(f"{BASE_URL}/api/schedule-assignment-plans", timeout=15)
    a_exists = any(p["name"] == PLAN_A_NAME for p in r_before.json())
    assert a_exists, "Plan A debería seguir existiendo tras test 2"

    r = client.post(f"{BASE_URL}/api/schedule-assignment-plans", json={
        "name": PLAN_B_NAME, "from_date": FROM_B, "to_date": TO_B,
        "user_ids": [u1["user_id"]], "row_order": [u1["user_id"]],
        "overwrite": True,
        "assignments": [{"user_id": u1["user_id"], "date": "2027-03-08",
                         "kind": "novelty", "novelty_type": "vacation"}],
    }, timeout=15)
    assert r.status_code == 200, r.text

    # Plan A should be gone
    r2 = client.get(f"{BASE_URL}/api/schedule-assignment-plans", timeout=15)
    names = {p["name"] for p in r2.json()}
    assert PLAN_A_NAME not in names
    assert PLAN_B_NAME in names

    # Assignments now = only B's
    asgs = _get_assignments(client, [u1["user_id"]], "2027-03-01", "2027-03-31")
    # Old 03-03 shift should be gone (out of B's range 03-05→03-15, so pruned by B save? Actually 03-03 < 03-05, so it's outside B's user_ids range. But _replace_plan_assignments deletes for universe of users in [B.from,B.to]. 03-03 is outside that. And _prune_out_of_range_assignments uses plan B's user_ids and its range - purges outside. u1 in B, so 03-03 IS outside [03-05,03-15], will be pruned.)
    dates = {a["date"] for a in asgs}
    assert "2027-03-08" in dates
    assert "2027-03-03" not in dates, f"Old assignment should have been pruned; got {dates}"


# ---------- 4) PUT reemplaza EXACTO ----------
def test_4_put_replaces_exact(client, eligible_users, a_schedule):
    u1 = eligible_users[0]
    # Find plan B
    r = client.get(f"{BASE_URL}/api/schedule-assignment-plans", timeout=15)
    plan_b = next(p for p in r.json() if p["name"] == PLAN_B_NAME)

    # Add 2 assignments via PUT
    body = {
        "name": PLAN_B_NAME, "from_date": FROM_B, "to_date": TO_B,
        "user_ids": [u1["user_id"]], "row_order": [u1["user_id"]],
        "assignments": [
            {"user_id": u1["user_id"], "date": "2027-03-08",
             "kind": "novelty", "novelty_type": "vacation"},
            {"user_id": u1["user_id"], "date": "2027-03-09",
             "kind": "shift", "schedule_id": a_schedule["schedule_id"]},
        ],
    }
    r2 = client.put(f"{BASE_URL}/api/schedule-assignment-plans/{plan_b['plan_id']}",
                    json=body, timeout=15)
    assert r2.status_code == 200, r2.text
    asgs = _get_assignments(client, [u1["user_id"]], FROM_B, TO_B)
    dates = {a["date"] for a in asgs}
    assert dates == {"2027-03-08", "2027-03-09"}

    # Now PUT with ONE cell removed (only 03-09 remains)
    body2 = dict(body)
    body2["assignments"] = [
        {"user_id": u1["user_id"], "date": "2027-03-09",
         "kind": "shift", "schedule_id": a_schedule["schedule_id"]},
    ]
    r3 = client.put(f"{BASE_URL}/api/schedule-assignment-plans/{plan_b['plan_id']}",
                    json=body2, timeout=15)
    assert r3.status_code == 200, r3.text
    asgs2 = _get_assignments(client, [u1["user_id"]], FROM_B, TO_B)
    dates2 = {a["date"] for a in asgs2}
    assert dates2 == {"2027-03-09"}, f"Removed cell should not reappear; got {dates2}"


# ---------- 5) Regresión: bulk y clear con cells siguen funcionando ----------
def test_5_bulk_and_clear_legacy_cells(client, eligible_users, a_schedule):
    u1, u2 = eligible_users
    # bulk with cells
    r = client.post(f"{BASE_URL}/api/schedule-assignments/bulk", json={
        "user_ids": [], "dates": [],
        "kind": "shift", "schedule_id": a_schedule["schedule_id"],
        "cells": [
            {"user_id": u1["user_id"], "date": "2027-03-20"},
            {"user_id": u2["user_id"], "date": "2027-03-21"},
        ],
    }, timeout=15)
    assert r.status_code == 200, r.text
    asgs = _get_assignments(client, [u1["user_id"], u2["user_id"]], "2027-03-20", "2027-03-21")
    pairs = {(a["user_id"], a["date"]) for a in asgs}
    assert (u1["user_id"], "2027-03-20") in pairs
    assert (u2["user_id"], "2027-03-21") in pairs
    assert (u1["user_id"], "2027-03-21") not in pairs  # no cartesian
    # clear with cells
    r2 = client.post(f"{BASE_URL}/api/schedule-assignments/clear", json={
        "user_ids": [], "dates": [],
        "cells": [
            {"user_id": u1["user_id"], "date": "2027-03-20"},
            {"user_id": u2["user_id"], "date": "2027-03-21"},
        ],
    }, timeout=15)
    assert r2.status_code == 200, r2.text
    asgs2 = _get_assignments(client, [u1["user_id"], u2["user_id"]], "2027-03-20", "2027-03-21")
    assert len(asgs2) == 0


# ---------- 6) Matriz especial refleja assignments del plan ----------
def test_6_matrix_special_reflects_plan(client, eligible_users):
    u1 = eligible_users[0]
    r = client.get(f"{BASE_URL}/api/reports/matrix",
                   params={"schedule_id": "__special",
                           "from_date": FROM_B, "to_date": TO_B},
                   timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # find u1's row
    rows = data.get("rows") or data.get("users") or []
    user_row = next((row for row in rows if row.get("user_id") == u1["user_id"]), None)
    assert user_row is not None, f"user {u1['user_id']} not in matrix rows"
    # Expect an entry for 2027-03-09 marked as shift-related (future or similar)
    days = user_row.get("cells") or user_row.get("days") or {}
    d09 = days.get("2027-03-09") if isinstance(days, dict) else None
    if d09 is None and isinstance(days, list):
        d09 = next((d for d in days if d.get("date") == "2027-03-09"), None)
    assert d09 is not None, f"2027-03-09 missing in matrix row: {user_row}"
    assert d09.get("status") == "future", f"Expected 'future' for shift day, got {d09}"
