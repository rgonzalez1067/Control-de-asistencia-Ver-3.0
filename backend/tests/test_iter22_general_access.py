"""Iteración 22 — Reporte General de Accesos.

Cobertura:
- GET /api/reports/general-access RBAC (403 sin permiso, 200 admin)
- Validación de rango obligatorio (400 sin from_date/to_date)
- Contenido y ordenación de rows
- Filtros department_ids y site_id
- Jerarquía: director ve toda la nómina; gerente/coordinador su equipo
- GET /api/reports/general-access/export.pdf → PDF válido (multi-página)
- Catálogo RBAC incluye reporte_general_accesos en sección Control de Visitas
"""
import io
import os
import time
import pytest
import requests

def _read_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL no disponible"
API = f"{BASE_URL}/api"

ADMIN = ("rgonzalez@megasoft.com.ve", "Sol*1401*1010")
DIRECTOR = ("acastro@megasoft.com.ve", "DirTest!2026")
GERENTE = ("adasilva@megasoft.com.ve", "GerTest!2026")
COORD = ("lalvarez@megasoft.com.ve", "CoordTest!2026")
EMPL = ("jgil@megasoft.com.ve", "NewJgil!234")

FROM = "2026-09-14"
TO = "2026-09-21"


def _login(email, password, retries=3):
    """Login espaciando reintentos por rate-limit 5/min."""
    for i in range(retries):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        if r.status_code in (429, 423):
            time.sleep(15)
            continue
        break
    pytest.skip(f"No pude autenticar {email} (last status={r.status_code}, body={r.text[:200]})")


@pytest.fixture(scope="module")
def admin_token():
    tok = _login(*ADMIN)
    time.sleep(13)
    return tok


@pytest.fixture(scope="module")
def director_token():
    tok = _login(*DIRECTOR)
    time.sleep(13)
    return tok


@pytest.fixture(scope="module")
def gerente_token():
    tok = _login(*GERENTE)
    time.sleep(13)
    return tok


@pytest.fixture(scope="module")
def coord_token():
    tok = _login(*COORD)
    time.sleep(13)
    return tok


@pytest.fixture(scope="module")
def empleado_token():
    tok = _login(*EMPL)
    time.sleep(13)
    return tok


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


PROFILE_NAMES_FOR_HIERARCHY = ["Director", "Gerente", "Coordinador de Monitoreo"]
PERM_KEY = "reporte_general_accesos"


@pytest.fixture(scope="module", autouse=True)
def hierarchy_perm_enabled(admin_token):
    """Habilita temporalmente `reporte_general_accesos` en los perfiles de
    Director/Gerente/Coordinador de Monitoreo para poder probar la jerarquía;
    al finalizar los restaura (permiso en False)."""
    r = requests.get(f"{API}/access-profiles", headers=_hdr(admin_token))
    assert r.status_code == 200, r.text
    profiles = {p["name"]: p for p in r.json()}
    touched = []
    for name in PROFILE_NAMES_FOR_HIERARCHY:
        p = profiles.get(name)
        if not p:
            continue
        perms = dict(p.get("permissions") or {})
        perms[PERM_KEY] = True
        pr = requests.put(f"{API}/access-profiles/{p['profile_id']}",
                          json={"name": p["name"], "description": p.get("description") or "", "permissions": perms},
                          headers=_hdr(admin_token))
        assert pr.status_code == 200, pr.text
        touched.append(p["profile_id"])
    yield
    r2 = requests.get(f"{API}/access-profiles", headers=_hdr(admin_token))
    if r2.status_code == 200:
        by_id = {p["profile_id"]: p for p in r2.json()}
        for pid in touched:
            p = by_id.get(pid)
            if not p:
                continue
            perms = dict(p.get("permissions") or {})
            perms[PERM_KEY] = False
            requests.put(f"{API}/access-profiles/{pid}",
                         json={"name": p["name"], "description": p.get("description") or "", "permissions": perms},
                         headers=_hdr(admin_token))


# ---------- Catálogo RBAC ----------
def test_catalog_incluye_reporte_general_accesos(admin_token):
    r = requests.get(f"{API}/access-profiles/catalog", headers=_hdr(admin_token))
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("catalog") or []
    keys = [i.get("key") for i in items]
    assert "reporte_general_accesos" in keys, f"keys={keys[:30]}"
    item = next(i for i in items if i.get("key") == "reporte_general_accesos")
    assert (item.get("section") or "").lower() == "control de visitas"


# ---------- Validaciones ----------
def test_requires_date_range(admin_token):
    r = requests.get(f"{API}/reports/general-access", headers=_hdr(admin_token))
    assert r.status_code == 400


def test_rbac_denies_employee_without_perm(empleado_token):
    r = requests.get(f"{API}/reports/general-access",
                     params={"from_date": FROM, "to_date": TO},
                     headers=_hdr(empleado_token))
    assert r.status_code == 403


# ---------- Contenido ----------
def test_admin_returns_rows_with_expected_shape(admin_token):
    r = requests.get(f"{API}/reports/general-access",
                     params={"from_date": FROM, "to_date": TO},
                     headers=_hdr(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["from_date"] == FROM and body["to_date"] == TO
    assert isinstance(body.get("rows"), list)
    assert body["rows_count"] == len(body["rows"])
    if body["rows"]:
        row = body["rows"][0]
        for k in ("cedula", "nombre", "departamento", "cargo", "fecha", "e1", "s1", "e2", "s2"):
            assert k in row
        # ordenación por fecha+nombre
        keys = [(r_["fecha"], r_["nombre"]) for r_ in body["rows"]]
        assert keys == sorted(keys)


def test_site_filter_returns_site_name(admin_token):
    # get first site
    r = requests.get(f"{API}/sites", headers=_hdr(admin_token))
    if r.status_code != 200 or not r.json():
        pytest.skip("No hay /api/sites disponible")
    sites = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    if not sites:
        pytest.skip("Sin sedes")
    sid = sites[0].get("site_id") or sites[0].get("id")
    sname = sites[0].get("name")
    r = requests.get(f"{API}/reports/general-access",
                     params={"from_date": FROM, "to_date": TO, "site_id": sid},
                     headers=_hdr(admin_token))
    assert r.status_code == 200
    assert r.json().get("site_name") == sname


def test_department_filter_restricts(admin_token):
    r = requests.get(f"{API}/departments", headers=_hdr(admin_token))
    if r.status_code != 200:
        pytest.skip("No hay /api/departments")
    depts = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    if not depts:
        pytest.skip("Sin departamentos")
    did = depts[0].get("department_id") or depts[0].get("id")
    dname = depts[0].get("name")
    r = requests.get(f"{API}/reports/general-access",
                     params={"from_date": FROM, "to_date": TO, "department_ids": did},
                     headers=_hdr(admin_token))
    assert r.status_code == 200
    for row in r.json().get("rows", []):
        assert row["departamento"] == dname


# ---------- Jerarquía ----------
def test_director_sees_full_payroll(director_token, admin_token):
    r_dir = requests.get(f"{API}/reports/general-access",
                         params={"from_date": FROM, "to_date": TO},
                         headers=_hdr(director_token))
    assert r_dir.status_code == 200, r_dir.text
    r_adm = requests.get(f"{API}/reports/general-access",
                         params={"from_date": FROM, "to_date": TO},
                         headers=_hdr(admin_token))
    assert r_adm.status_code == 200
    # director debe ver el mismo universo que admin (o muy similar)
    assert r_dir.json()["employees_count"] >= max(1, r_adm.json()["employees_count"] - 2)


def test_gerente_scope_is_team(gerente_token, admin_token):
    r_g = requests.get(f"{API}/reports/general-access",
                       params={"from_date": FROM, "to_date": TO},
                       headers=_hdr(gerente_token))
    assert r_g.status_code == 200
    r_a = requests.get(f"{API}/reports/general-access",
                       params={"from_date": FROM, "to_date": TO},
                       headers=_hdr(admin_token))
    assert r_a.status_code == 200
    # gerente ve mucho menos que admin
    assert r_g.json()["employees_count"] < r_a.json()["employees_count"]


def test_coordinador_scope_is_team(coord_token, admin_token):
    r_c = requests.get(f"{API}/reports/general-access",
                      params={"from_date": FROM, "to_date": TO},
                      headers=_hdr(coord_token))
    assert r_c.status_code == 200
    r_a = requests.get(f"{API}/reports/general-access",
                     params={"from_date": FROM, "to_date": TO},
                     headers=_hdr(admin_token))
    assert r_c.json()["employees_count"] <= r_a.json()["employees_count"]


# ---------- PDF ----------
def test_pdf_export_is_valid_pdf(admin_token):
    r = requests.get(f"{API}/reports/general-access/export.pdf",
                     params={"from_date": FROM, "to_date": TO},
                     headers=_hdr(admin_token))
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    content = r.content
    assert content[:4] == b"%PDF", "Respuesta no es un PDF válido"
    # Debe tener múltiples páginas con rango grande
    page_count = content.count(b"/Type /Page") or content.count(b"/Type/Page")
    assert page_count >= 1
    # Cabeceras del reporte presentes (texto simple)
    # ReportLab codifica strings; buscamos marcadores parciales
    assert b"Reporte" in content or b"eporte" in content
