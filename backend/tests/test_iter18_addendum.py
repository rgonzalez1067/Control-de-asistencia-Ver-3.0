"""Iteración 18 — Adenda de corrección de INTEGRIDAD DE DATOS en Asignación
de Horarios ↔ Matriz de Asistencia.

Cubre:
  - POST /schedule-assignments/bulk con `cells` (selección exacta, sin producto
    cartesiano)
  - POST /schedule-assignments/clear con `cells` exactos
  - PUT /schedule-assignment-plans/{id} con purga fuera-de-rango
  - POST/PUT plan persiste `row_order` y GET lo devuelve
  - Matriz de Asistencia (schedule_id=__special): shift futuro → future;
    novedad asignada → novelty_full; celda vacía de usuario en plan → day_off
  - Regresión: bulk legacy (user_ids + dates sin cells) sigue haciendo
    producto cartesiano
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


# ------------------- fixtures ---------------------
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
    r = client.get(f"{BASE_URL}/api/schedule-assignments/eligible-users",
                   timeout=15)
    assert r.status_code == 200, r.text
    users = r.json()
    # role employee (no admin/kiosk) y con user_id
    emps = [u for u in users if u.get("role") == "employee"][:3]
    assert len(emps) >= 2, "Se requieren al menos 2 empleados elegibles"
    return emps


@pytest.fixture(scope="module")
def a_schedule_id(client):
    r = client.get(f"{BASE_URL}/api/schedules", timeout=15)
    assert r.status_code == 200
    schs = r.json()
    assert schs, "Se requiere al menos un horario existente para las pruebas"
    return schs[0]["schedule_id"]


# Fechas de trabajo — futuras (2027) para no chocar con planes reales
D1 = "2027-03-01"
D2 = "2027-03-02"
D3 = "2027-03-03"
D_OUT = "2027-04-15"  # fuera del rango original del plan (test de purge)


@pytest.fixture(scope="module")
def cleanup_after(client, eligible_users):
    # yield primero, cleanup al final
    created = {"plan_ids": [], "user_ids": [u["user_id"] for u in eligible_users]}
    yield created
    # Cleanup: borrar planes creados y todas las asignaciones futuras de los usuarios
    for pid in created["plan_ids"]:
        try:
            client.delete(f"{BASE_URL}/api/schedule-assignment-plans/{pid}",
                          timeout=10)
        except Exception:
            pass
    # Borrar cualquier asignación 2027 restante para los usuarios de prueba
    try:
        client.post(
            f"{BASE_URL}/api/schedule-assignments/clear",
            json={"user_ids": created["user_ids"],
                  "dates": [f"2027-03-{d:02d}" for d in range(1, 32)] +
                           [f"2027-04-{d:02d}" for d in range(1, 31)] +
                           [f"2027-05-{d:02d}" for d in range(1, 32)]},
            timeout=15,
        )
    except Exception:
        pass


# =============================================================
# 1) Bulk con `cells` exactos → EXACTO 2 documentos (no 4)
# =============================================================
def test_bulk_with_cells_creates_exact_pairs(client, eligible_users, a_schedule_id, cleanup_after):
    u1, u2 = eligible_users[0]["user_id"], eligible_users[1]["user_id"]

    # Limpieza previa
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2]}, timeout=10)

    r = client.post(
        f"{BASE_URL}/api/schedule-assignments/bulk",
        json={
            "user_ids": [u1, u2],
            "dates": [D1, D2],
            "kind": "shift",
            "schedule_id": a_schedule_id,
            "cells": [{"user_id": u1, "date": D1},
                      {"user_id": u2, "date": D2}],
        },
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["affected"] == 2, f"Esperado 2 pairs, got {body}"

    # Verificar por GET
    g = client.get(
        f"{BASE_URL}/api/schedule-assignments",
        params={"from_date": D1, "to_date": D2, "user_ids": f"{u1},{u2}"},
        timeout=15,
    )
    assert g.status_code == 200
    docs = g.json()
    pairs = {(d["user_id"], d["date"]) for d in docs}
    assert (u1, D1) in pairs and (u2, D2) in pairs
    assert (u1, D2) not in pairs, "Celda fantasma u1-D2 no debería existir"
    assert (u2, D1) not in pairs, "Celda fantasma u2-D1 no debería existir"


# =============================================================
# 2) Clear con `cells` exactos → borra sólo esos pares
# =============================================================
def test_clear_with_cells_deletes_only_those_pairs(client, eligible_users, a_schedule_id):
    u1, u2 = eligible_users[0]["user_id"], eligible_users[1]["user_id"]

    # Sembrar 4 pares con legacy (producto cartesiano)
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2]}, timeout=10)
    r = client.post(
        f"{BASE_URL}/api/schedule-assignments/bulk",
        json={"user_ids": [u1, u2], "dates": [D1, D2],
              "kind": "shift", "schedule_id": a_schedule_id},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["affected"] == 4

    # Ahora borrar sólo dos pares específicos
    rc = client.post(
        f"{BASE_URL}/api/schedule-assignments/clear",
        json={"user_ids": [u1, u2], "dates": [D1, D2],
              "cells": [{"user_id": u1, "date": D2},
                        {"user_id": u2, "date": D1}]},
        timeout=15,
    )
    assert rc.status_code == 200
    assert rc.json()["deleted"] == 2

    g = client.get(
        f"{BASE_URL}/api/schedule-assignments",
        params={"from_date": D1, "to_date": D2, "user_ids": f"{u1},{u2}"},
        timeout=15,
    )
    pairs = {(d["user_id"], d["date"]) for d in g.json()}
    assert pairs == {(u1, D1), (u2, D2)}

    # Cleanup
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2]}, timeout=10)


# =============================================================
# 3) Regresión: bulk legacy sigue haciendo producto cartesiano
# =============================================================
def test_bulk_legacy_cartesian_still_works(client, eligible_users, a_schedule_id):
    u1, u2 = eligible_users[0]["user_id"], eligible_users[1]["user_id"]
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2, D3]}, timeout=10)

    r = client.post(
        f"{BASE_URL}/api/schedule-assignments/bulk",
        json={"user_ids": [u1, u2], "dates": [D1, D2, D3],
              "kind": "shift", "schedule_id": a_schedule_id},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 6

    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2, D3]}, timeout=10)


# =============================================================
# 4) Plan persiste row_order y GET lo devuelve
# =============================================================
def test_plan_persists_row_order(client, eligible_users, cleanup_after):
    u1, u2 = eligible_users[0]["user_id"], eligible_users[1]["user_id"]
    # ordenamos u2 primero, luego u1 (orden invertido)
    payload = {
        "name": "TEST_ZZ_row_order_addendum",
        "from_date": D1,
        "to_date": D3,
        "user_ids": [u1, u2],
        "row_order": [u2, u1],
    }
    r = client.post(f"{BASE_URL}/api/schedule-assignment-plans",
                    json=payload, timeout=15)
    assert r.status_code == 200, r.text
    plan = r.json()
    cleanup_after["plan_ids"].append(plan["plan_id"])
    assert plan["row_order"] == [u2, u1]

    g = client.get(f"{BASE_URL}/api/schedule-assignment-plans", timeout=15)
    found = [p for p in g.json() if p["plan_id"] == plan["plan_id"]]
    assert found and found[0]["row_order"] == [u2, u1]


# =============================================================
# 5) PUT plan con rango acortado → purga asignaciones fuera de rango
# =============================================================
def test_put_plan_prunes_out_of_range_assignments(client, eligible_users, a_schedule_id, cleanup_after):
    u1 = eligible_users[0]["user_id"]
    # crear plan con rango amplio
    r = client.post(
        f"{BASE_URL}/api/schedule-assignment-plans",
        json={"name": "TEST_ZZ_prune_addendum",
              "from_date": D1, "to_date": D_OUT,
              "user_ids": [u1], "row_order": [u1], "overwrite": True},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    plan = r.json()
    cleanup_after["plan_ids"].append(plan["plan_id"])

    # Sembrar 2 asignaciones: una dentro (D1) y otra fuera del futuro rango acortado (D_OUT)
    client.post(f"{BASE_URL}/api/schedule-assignments/bulk",
                json={"user_ids": [u1], "dates": [D1, D_OUT],
                      "kind": "shift", "schedule_id": a_schedule_id,
                      "cells": [{"user_id": u1, "date": D1},
                                {"user_id": u1, "date": D_OUT}]},
                timeout=15)

    # Verificar que ambas existen
    g0 = client.get(f"{BASE_URL}/api/schedule-assignments",
                    params={"from_date": D1, "to_date": D_OUT,
                            "user_ids": u1}, timeout=15)
    dates0 = {d["date"] for d in g0.json()}
    assert D1 in dates0 and D_OUT in dates0

    # PUT plan → acortar rango a [D1, D3]
    ru = client.put(
        f"{BASE_URL}/api/schedule-assignment-plans/{plan['plan_id']}",
        json={"name": "TEST_ZZ_prune_addendum",
              "from_date": D1, "to_date": D3,
              "user_ids": [u1], "row_order": [u1], "overwrite": True},
        timeout=15,
    )
    assert ru.status_code == 200, ru.text

    # La asignación en D_OUT debió purgarse; D1 sigue
    g1 = client.get(f"{BASE_URL}/api/schedule-assignments",
                    params={"from_date": D1, "to_date": D_OUT,
                            "user_ids": u1}, timeout=15)
    dates1 = {d["date"] for d in g1.json()}
    assert D1 in dates1, "D1 debía conservarse"
    assert D_OUT not in dates1, "D_OUT (fuera de rango) debía ser purgado"

    # Cleanup
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1], "dates": [D1]}, timeout=10)


# =============================================================
# 6) Matriz de Asistencia con schedule_id=__special
#    - futuro con shift → 'future'
#    - novedad asignada → 'novelty_full'
#    - celda vacía de usuario en plan → 'day_off'
# =============================================================
def test_matrix_special_statuses_future_and_novelty_and_day_off(client, eligible_users, a_schedule_id, cleanup_after):
    u1, u2 = eligible_users[0]["user_id"], eligible_users[1]["user_id"]

    # Crear plan que incluye u1,u2 abarcando D1..D3
    r = client.post(
        f"{BASE_URL}/api/schedule-assignment-plans",
        json={"name": "TEST_ZZ_matrix_addendum",
              "from_date": D1, "to_date": D3,
              "user_ids": [u1, u2], "row_order": [u1, u2], "overwrite": True},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    plan = r.json()
    cleanup_after["plan_ids"].append(plan["plan_id"])

    # Limpieza previa
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2, D3]}, timeout=10)

    # u1@D1 → shift (futuro) — celdas exactas
    client.post(f"{BASE_URL}/api/schedule-assignments/bulk",
                json={"user_ids": [u1], "dates": [D1],
                      "kind": "shift", "schedule_id": a_schedule_id,
                      "cells": [{"user_id": u1, "date": D1}]},
                timeout=15)
    # u2@D2 → novedad remote
    client.post(f"{BASE_URL}/api/schedule-assignments/bulk",
                json={"user_ids": [u2], "dates": [D2],
                      "kind": "novelty", "novelty_type": "remote",
                      "cells": [{"user_id": u2, "date": D2}]},
                timeout=15)

    # Matriz especial
    m = client.get(f"{BASE_URL}/api/reports/matrix",
                   params={"from_date": D1, "to_date": D3,
                           "schedule_id": "__special",
                           "user_ids": f"{u1},{u2}"},
                   timeout=30)
    assert m.status_code == 200, m.text
    data = m.json()
    rows = data.get("rows") or data.get("users") or []
    # index by user_id
    by_uid = {r["user_id"]: r for r in rows if r.get("user_id")}
    assert u1 in by_uid and u2 in by_uid, f"Filas del plan no presentes: {list(by_uid)}"

    cells_u1 = by_uid[u1].get("cells", {})
    cells_u2 = by_uid[u2].get("cells", {})

    # u1@D1: shift asignado → status 'future' (NO 'day_off')
    assert cells_u1.get(D1, {}).get("status") == "future", \
        f"u1@D1 esperado 'future', got {cells_u1.get(D1)}"
    # u1@D2 y u1@D3 vacíos → 'day_off'
    assert cells_u1.get(D2, {}).get("status") == "day_off", cells_u1.get(D2)
    assert cells_u1.get(D3, {}).get("status") == "day_off", cells_u1.get(D3)

    # u2@D2: novedad remote → 'novelty_full'
    assert cells_u2.get(D2, {}).get("status") == "novelty_full", cells_u2.get(D2)
    assert cells_u2.get(D2, {}).get("novelty_type") == "remote"
    # u2@D1 y u2@D3 vacíos → 'day_off'
    assert cells_u2.get(D1, {}).get("status") == "day_off", cells_u2.get(D1)
    assert cells_u2.get(D3, {}).get("status") == "day_off", cells_u2.get(D3)

    # Cleanup asignaciones
    client.post(f"{BASE_URL}/api/schedule-assignments/clear",
                json={"user_ids": [u1, u2], "dates": [D1, D2, D3]}, timeout=10)
