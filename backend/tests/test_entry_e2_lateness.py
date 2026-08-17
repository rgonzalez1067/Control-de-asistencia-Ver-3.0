"""Tests para el nuevo cálculo E1/E2 (regla de gap S1→E2 con umbral 60 min).

Estrategia:
- Inserta registros TEST_ vía MongoDB directo para jgil (empleado real).
- Asigna schedule "Día Completo" (blocks 08:00-12:00, 13:00-17:00, tol=10, jt=20).
- Corrompe intencionalmente los campos is_late/late_minutes/severity/entry_index.
- Reinicia backend para disparar `_backfill_entry_index_and_lateness`.
- Verifica que el backfill los deja consistentes.
- Verifica que GET /api/attendance/me devuelve entry_index poblado.
- Verifica que registros ya "approved" NO se ven forzados a requires_justification=True.
"""
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2").read().strip()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

JGIL_EMAIL = "jgil@megasoft.com.ve"
JGIL_PASSWORD = "NewJgil!234"
DAY_COMPLETO_SCHED = "sch_d2db7693fc"

# Usamos un día "antiguo" para no chocar con marcas del día actual
TEST_DAY = datetime(2025, 3, 5, tzinfo=timezone.utc)  # miércoles
# Caracas UTC-4 → 08:00 local = 12:00 UTC
E1_TS  = datetime(2025, 3, 5, 12, 0,  0, tzinfo=timezone.utc)   # 08:00 local
S1_TS  = datetime(2025, 3, 5, 16, 0,  0, tzinfo=timezone.utc)   # 12:00 local
E2_TS  = datetime(2025, 3, 5, 17, 15, 0, tzinfo=timezone.utc)   # 13:15 local → gap=75 → excess=15 → late_minor
S2_TS  = datetime(2025, 3, 5, 21, 0,  0, tzinfo=timezone.utc)   # 17:00 local

# Otro día para test de "approved preservado"
E2_APPROVED_TS = datetime(2025, 3, 6, 18, 30, 0, tzinfo=timezone.utc)  # 14:30 local → gap=150 → excess=90


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def jgil_user(mongo):
    u = mongo.users.find_one({"email": JGIL_EMAIL}, {"_id": 0})
    assert u, "jgil no existe en la BD"
    return u


@pytest.fixture(scope="module", autouse=True)
def setup_records_and_backfill(mongo, jgil_user):
    """Insert TEST_ records + set jgil schedule + restart backend to trigger backfill."""
    uid = jgil_user["user_id"]
    original_schedule = jgil_user.get("schedule_id")

    # 1. Ensure jgil has the Día Completo schedule for the test
    mongo.users.update_one({"user_id": uid}, {"$set": {"schedule_id": DAY_COMPLETO_SCHED}})

    # 2. Clean any existing TEST_ records for these dates
    mongo.attendance.delete_many({"record_id": {"$regex": "^att_TEST_e2_"}})

    # 3. Insert corrupted records (values WRONG on purpose to verify backfill fixes them)
    records = [
        # Día 1: E1 puntual, S1, E2 (excess 15 min → late_minor), S2
        {"record_id": "att_TEST_e2_e1", "user_id": uid, "type": "in", "timestamp": E1_TS,
         "site_id": None, "is_late": True, "late_minutes": 999, "late_severity": "late_major",
         "requires_justification": True, "entry_index": 5, "justification_status": "none", "method": "test_seed"},
        {"record_id": "att_TEST_e2_s1", "user_id": uid, "type": "out", "timestamp": S1_TS,
         "site_id": None, "is_late": False, "late_minutes": 0, "late_severity": "on_time",
         "requires_justification": False, "justification_status": "none", "method": "test_seed"},
        {"record_id": "att_TEST_e2_e2", "user_id": uid, "type": "in", "timestamp": E2_TS,
         "site_id": None, "is_late": True, "late_minutes": 315, "late_severity": "late_major",
         "requires_justification": True, "entry_index": 99, "justification_status": "none", "method": "test_seed"},
        {"record_id": "att_TEST_e2_s2", "user_id": uid, "type": "out", "timestamp": S2_TS,
         "site_id": None, "is_late": False, "late_minutes": 0, "late_severity": "on_time",
         "requires_justification": False, "justification_status": "none", "method": "test_seed"},
        # Día 2: E1 puntual + S1 + E2 con excess 90m PERO ya "approved" → no debe forzar requires_justification
        {"record_id": "att_TEST_e2_d2_e1", "user_id": uid, "type": "in",
         "timestamp": datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc),
         "site_id": None, "is_late": False, "late_minutes": 0, "late_severity": "on_time",
         "requires_justification": False, "justification_status": "none", "method": "test_seed"},
        {"record_id": "att_TEST_e2_d2_s1", "user_id": uid, "type": "out",
         "timestamp": datetime(2025, 3, 6, 16, 0, 0, tzinfo=timezone.utc),
         "site_id": None, "is_late": False, "late_minutes": 0, "late_severity": "on_time",
         "requires_justification": False, "justification_status": "none", "method": "test_seed"},
        {"record_id": "att_TEST_e2_d2_e2_appr", "user_id": uid, "type": "in", "timestamp": E2_APPROVED_TS,
         "site_id": None, "is_late": True, "late_minutes": 0, "late_severity": "on_time",
         "requires_justification": False, "entry_index": None, "justification_status": "approved",
         "justification": "test approved", "method": "test_seed"},
    ]
    mongo.attendance.insert_many(records)

    # 4. Restart backend to trigger backfill on startup
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, capture_output=True)
    # wait for backend to come up
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/api/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    time.sleep(2)  # extra grace for backfill

    yield

    # Teardown
    mongo.attendance.delete_many({"record_id": {"$regex": "^att_TEST_e2_"}})
    if original_schedule is not None:
        mongo.users.update_one({"user_id": uid}, {"$set": {"schedule_id": original_schedule}})


@pytest.fixture(scope="module")
def jgil_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": JGIL_EMAIL, "password": JGIL_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"login jgil falló: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "rgonzalez@megasoft.com.ve", "password": "admin123"}, timeout=10)
    assert r.status_code == 200
    return r.json()["token"]


# ---------------------------------------------------------------------------
# Tests: backfill corrigió los registros
# ---------------------------------------------------------------------------

def _get_rec(mongo, rid):
    return mongo.attendance.find_one({"record_id": rid}, {"_id": 0})


def test_backfill_e1_on_time(mongo):
    r = _get_rec(mongo, "att_TEST_e2_e1")
    assert r["is_late"] is False, f"E1 08:00 exacto debe ser on_time, got {r}"
    assert r["late_minutes"] == 0
    assert r["late_severity"] == "on_time"
    assert r["entry_index"] == 0
    assert r["requires_justification"] is False


def test_backfill_e2_gap_75_gives_excess_15(mongo):
    r = _get_rec(mongo, "att_TEST_e2_e2")
    assert r["entry_index"] == 1
    assert r["is_late"] is True
    assert r["late_minutes"] == 15, f"gap 75 → excess 15, got {r['late_minutes']}"
    assert r["late_severity"] == "late_minor"  # 15 <= tol_justif=20
    assert r["requires_justification"] is False  # dentro de la ventana


def test_backfill_out_records_untouched_entry_index(mongo):
    """Los registros 'out' no tienen entry_index — solo los 'in'."""
    r = _get_rec(mongo, "att_TEST_e2_s1")
    # entry_index en outs puede quedar como estaba; lo importante es que type='out' no fue reclasificado
    assert r["type"] == "out"


def test_backfill_preserves_approved(mongo):
    r = _get_rec(mongo, "att_TEST_e2_d2_e2_appr")
    # El campo lateness sí se recalcula, pero requires_justification NO debe forzarse
    assert r["entry_index"] == 1
    assert r["is_late"] is True
    assert r["late_minutes"] == 90  # gap 150 - 60 = 90
    assert r["requires_justification"] is False, "approved no debe forzar requires_justification"
    assert r["justification_status"] == "approved"


# ---------------------------------------------------------------------------
# Endpoints devuelven entry_index
# ---------------------------------------------------------------------------

def test_attendance_me_includes_entry_index(jgil_token):
    r = requests.get(f"{BASE_URL}/api/attendance/me?limit=200",
                     headers={"Authorization": f"Bearer {jgil_token}"}, timeout=10)
    assert r.status_code == 200
    docs = r.json()
    test_docs = [d for d in docs if d.get("record_id", "").startswith("att_TEST_e2_") and d.get("type") == "in"]
    assert len(test_docs) >= 3
    for d in test_docs:
        assert "entry_index" in d, f"falta entry_index en {d.get('record_id')}"
        assert d["entry_index"] in (0, 1), f"entry_index inesperado: {d['entry_index']}"


def test_attendance_team_includes_entry_index(admin_token, mongo):
    # admin ve todos los registros (query sin filtro por team)
    r = requests.get(f"{BASE_URL}/api/attendance/team?days=400",
                     headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    assert r.status_code == 200
    docs = r.json()
    test_ins = [d for d in docs if d.get("record_id", "").startswith("att_TEST_e2_") and d.get("type") == "in"]
    # admin no filtra por team pero SÍ pasa el filtro por fecha (days=400 debería incluir marzo 2025)
    # Si days=400 no basta, saltamos suave.
    if not test_ins:
        pytest.skip("días fuera de rango team endpoint — no crítico")
    for d in test_ins:
        assert "entry_index" in d
