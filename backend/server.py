"""
Mega Soft Asistencia — FastAPI Backend
Fase 0: Puerto de la lógica del proyecto Mobile/Expo al stack Web/PWA.

Basado en el MIGRATION_BLUEPRINT.md (47 endpoints agrupados por dominio):
  Auth (7) · Users (8) · Settings (2) · Sites (5) · Departments (3)
  Schedules (3) · Kiosk (5) · Attendance (5) · Novelties (4)
  Reports/Stats (3) · Onboarding (1) · Root (1)
"""

from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import io
import csv
import json
import uuid
import math
import jwt
import bcrypt
import logging
import secrets
from bson import ObjectId
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Any, Dict, Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ------------------------------------------------------------------
# App / DB setup
# ------------------------------------------------------------------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "720"))
APP_TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/Caracas"))

client = AsyncIOMotorClient(MONGO_URL, tz_aware=True)
db = client[DB_NAME]

app = FastAPI(title="Mega Soft Asistencia API", version="0.1.0")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("megasoft.api")

# ------------------------------------------------------------------
# Rate limiting — mitiga fuerza bruta contra /auth/login y similares.
# Se instala en el `app` para poder decorar endpoints en cualquier router.
# ------------------------------------------------------------------
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse as _RLJSONResp
from starlette.requests import Request as _StarRequest

limiter = Limiter(key_func=get_remote_address, default_limits=[])
app.state.limiter = limiter


async def _rate_limit_exceeded_handler(request: _StarRequest, exc: RateLimitExceeded):
    return _RLJSONResp(
        status_code=429,
        content={"detail": "Demasiados intentos. Espera unos minutos e inténtalo de nuevo."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ------------------------------------------------------------------
# Audit log — persiste eventos sensibles (login exitoso/fallido y accesos
# admin) en la colección `audit_log`. Permite detectar accesos anómalos.
# ------------------------------------------------------------------
async def audit_log(event: str, request, *, user_id: Optional[str] = None,
                    email: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        ip = request.client.host if request and request.client else None
        fwd = request.headers.get("X-Forwarded-For", "") if request else ""
        real_ip = (fwd.split(",")[0].strip() if fwd else ip)
        ua = request.headers.get("User-Agent", "") if request else ""
        await db.audit_log.insert_one({
            "event": event,
            "user_id": user_id,
            "email": email,
            "ip": real_ip,
            "user_agent": ua[:300],
            "path": str(request.url.path) if request else None,
            "method": request.method if request else None,
            "timestamp": now_utc(),
            "extra": extra or {},
        })
    except Exception:  # noqa: BLE001 — auditar nunca debe tumbar el request
        logger.exception("audit_log write failed for event=%s", event)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str, size: int = 12) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:size]}"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


PASSWORD_POLICY_MSG = (
    "La contraseña debe tener al menos 8 caracteres, "
    "una mayúscula, una minúscula, un número y un carácter especial."
)


def validate_password_policy(pw: str) -> None:
    """Lanza HTTPException 400 si la contraseña no cumple la política."""
    import re as _re
    if not pw or len(pw) < 8:
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MSG)
    if not _re.search(r"[A-Z]", pw):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MSG)
    if not _re.search(r"[a-z]", pw):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MSG)
    if not _re.search(r"\d", pw):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MSG)
    if not _re.search(r"[^A-Za-z0-9]", pw):
        raise HTTPException(status_code=400, detail=PASSWORD_POLICY_MSG)


def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": int(now_utc().timestamp()),
        "exp": now_utc() + timedelta(minutes=JWT_ACCESS_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def sanitize_user(u: Dict[str, Any]) -> Dict[str, Any]:
    if not u:
        return u
    out = {k: v for k, v in u.items() if k not in {"_id", "password_hash", "pin_code_hash"}}
    return out


# ---------------------------------------------------------------------
# RBAC — helpers de permisos efectivos
# ---------------------------------------------------------------------
def _default_permissions_for_role(role: str) -> Dict[str, bool]:
    """Defaults cuando el usuario NO tiene perfil asignado.
    Reglas actualizadas (Feb 2026): el ROL ya no otorga menús por sí solo — todo
    va por perfil. Estos defaults sólo son fallback si el usuario todavía no
    tiene perfil:
      - admin: TODO ON (safety net; permite recuperar acceso a al menos un admin
        del sistema aunque no tenga perfil asignado).
      - kiosk: sólo `kiosco_activar` (los kiosk-users bypassean el sidebar).
      - resto (empleado/coordinador/gerente/director): sólo autoservicio básico
        (mi_carnet + historial). Sin perfil, no ven módulos administrativos ni
        de reporte — para eso necesitan un perfil asignado explícitamente.
    """
    role = (role or "employee").lower()
    if role == "admin":
        return {k: True for k in MENU_KEYS}
    if role == "kiosk":
        return {k: (k == "kiosco_activar") for k in MENU_KEYS}
    # Empleado, Coordinador, Gerente y Director comparten default sin perfil.
    allowed = {"mi_carnet", "historial"}
    return {k: (k in allowed) for k in MENU_KEYS}


async def compute_effective_permissions(user: Dict[str, Any]) -> Dict[str, bool]:
    """Devuelve `{menu_key: bool}` para todas las claves del catálogo.
       - Si el user tiene `access_profile_id` válido, usa **exclusivamente** ese
         perfil (sin importar su rol jerárquico — regla de negocio Feb 2026).
       - Si no tiene perfil, cae a los defaults por rol.
       - Nota: los admin sin perfil ven todo (safety net de bootstrap); si un
         admin tiene un perfil asignado, respeta ese perfil aunque signifique
         menos accesos (evita divergencia entre rol y perfil).
    """
    pid = user.get("access_profile_id")
    if pid:
        prof = await db.access_profiles.find_one({"profile_id": pid})
        if prof:
            overrides = prof.get("permissions", {}) or {}
            return {k: bool(overrides.get(k, False)) for k in MENU_KEYS}
    return _default_permissions_for_role(user.get("role") or "employee")


async def enrich_user_with_permissions(u: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper de `sanitize_user` que además calcula `effective_permissions`."""
    out = sanitize_user(u)
    if out:
        out["effective_permissions"] = await compute_effective_permissions(u)
    return out


def strip_mongo_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ------------------------------------------------------------------
# Auth dependency
# ------------------------------------------------------------------
_ROLE_ALIASES = {
    "admin": "admin", "administrador": "admin", "administradora": "admin",
    # Nuevos roles jerárquicos oficiales:
    "coordinador": "coordinador", "coordinadora": "coordinador",
    "gerente": "gerente",
    "director": "director", "directora": "director",
    # Rol legacy — se migra a "coordinador" en on_startup. Como alias sirve para
    # payloads viejos que aún manden "supervisor".
    "supervisor": "coordinador", "supervisora": "coordinador",
    "employee": "employee", "empleado": "employee", "empleada": "employee",
    "user": "employee",
    # "kiosk" es un rol operativo restringido: sólo activa el modo Kiosco de una
    # sede fija; no tiene acceso al panel administrativo. Ver seed en on_startup.
    "kiosk": "kiosk", "kiosco": "kiosk",
}

# Conjuntos de utilidad para chequeos de jerarquía.
LEADER_ROLES = {"coordinador", "gerente", "director"}         # No incluye admin
LEADER_OR_ADMIN_ROLES = LEADER_ROLES | {"admin"}


def normalize_role(value: Any) -> str:
    """Normaliza cualquier variante de rol a las claves canónicas
    ('admin' | 'coordinador' | 'gerente' | 'director' | 'employee' | 'kiosk')."""
    if not value:
        return "employee"
    key = str(value).strip().lower()
    return _ROLE_ALIASES.get(key, "employee")


async def get_current_user(request: Request) -> Dict[str, Any]:
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = await db.users.find_one({"user_id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    # NOTA sobre rol `kiosk`: la restricción es VISUAL (frontend redirige a
    # /kiosk/auto y no muestra menús admin). En backend no se filtran endpoints
    # a nivel global — así el Kiosco puede consumir roster, marcaje, visitas,
    # settings, etc. Los endpoints sensibles (crear usuarios, ajustes globales,
    # reportes) siguen protegidos con `require_roles("admin", ...)`, que
    # rechaza `kiosk` automáticamente.
    return user


def require_roles(*roles: str):
    async def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="No autorizado")
        return user
    return _dep


async def supervisor_scope_ids(user: Dict[str, Any]) -> List[str]:
    """Devuelve la lista de user_ids sobre los que un supervisor puede operar:
    su propio user_id + los de su equipo directo (users.supervisor_id == user_id)."""
    team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
    return [t["user_id"] for t in team] + [user["user_id"]]


# ------------------------------------------------------------------
# Pydantic models (request payloads)
# ------------------------------------------------------------------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    cedula: Optional[str] = None
    role: str = "employee"


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=200)


class ChangePinIn(BaseModel):
    """Autoservicio — el usuario debe presentar su contraseña actual para
    poder cambiar su PIN de marcaje en el kiosco."""
    current_password: str
    new_pin: str = Field(min_length=4, max_length=8)


class ResetPasswordIn(BaseModel):
    user_id: str
    new_password: str


# ---------------------------------------------------------------------
# RBAC — Perfiles de acceso (Access Profiles)
# ---------------------------------------------------------------------
# Catálogo canónico de opciones del menú/permisos. Es fuente única de verdad
# para el backend (seed + endpoints) y el frontend (grilla + sidebar).
# El diccionario retornado por GET /api/access-profiles/catalog conserva el
# orden de inserción, agrupando por sección.
SECTION_OPERACION = "Operación"

MENU_CATALOG: List[Dict[str, Any]] = [
    # Sección: Personal
    {"key": "mi_carnet",          "label": "Mi carnet",          "section": "Personal"},
    {"key": "historial",          "label": "Historial personal", "section": "Personal"},
    # Sección: Operación
    {"key": "kiosco_activar",     "label": "Activar Kiosco",     "section": SECTION_OPERACION},
    {"key": "matriz",             "label": "Reporte matricial",  "section": SECTION_OPERACION},
    {"key": "novedades",          "label": "Novedades",          "section": SECTION_OPERACION},
    {"key": "equipo",             "label": "Mi equipo",          "section": SECTION_OPERACION},
    {"key": "dashboard",          "label": "Dashboard",          "section": SECTION_OPERACION},
    # Sección: Visitas
    {"key": "visitas_agendar",    "label": "Agendar visita",     "section": "Visitas"},
    {"key": "visitas_historico",  "label": "Histórico de visitas", "section": "Visitas"},
    # Sección: Administración
    {"key": "empleados",          "label": "Empleados",          "section": "Administración"},
    {"key": "departamentos",      "label": "Departamentos",      "section": "Administración"},
    {"key": "sedes",              "label": "Sedes",              "section": "Administración"},
    {"key": "horarios",           "label": "Horarios",           "section": "Administración"},
    {"key": "asignar_horarios",   "label": "Asignación de horarios", "section": "Administración"},
    {"key": "reportes",           "label": "Reportes",           "section": "Administración"},
    {"key": "ajustes",            "label": "Ajustes",            "section": "Administración"},
    # Sección: Seguridad
    {"key": "seguridad_perfiles", "label": "Creación de perfiles de acceso", "section": "Seguridad"},
    {"key": "seguridad_permisos", "label": "Permisos de usuario", "section": "Seguridad"},
]
MENU_KEYS: List[str] = [x["key"] for x in MENU_CATALOG]


class AccessProfileIn(BaseModel):
    """Input para crear/actualizar un perfil de acceso.
    `permissions` es un dict `{menu_key: bool}` — cualquier clave desconocida se ignora."""
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=300)
    permissions: Dict[str, bool] = Field(default_factory=dict)


class AssignProfileIn(BaseModel):
    """Asigna un perfil a un usuario o a todos los usuarios de un departamento."""
    profile_id: Optional[str] = None  # null = desasignar


class AssignProfileToDeptIn(BaseModel):
    department_id: str
    profile_id: Optional[str] = None


class UserIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: EmailStr
    name: str
    role: str = "employee"
    cedula: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[str] = None
    site_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    schedule_id: Optional[str] = None
    picture: Optional[str] = None
    password: Optional[str] = None
    pin: Optional[str] = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    role: Optional[str] = None
    cedula: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[str] = None
    site_id: Optional[str] = None
    supervisor_id: Optional[str] = None
    schedule_id: Optional[str] = None
    picture: Optional[str] = None
    onboarded: Optional[bool] = None
    can_create_visits: Optional[bool] = None
    can_view_visit_logs: Optional[bool] = None
    can_manage_schedules: Optional[bool] = None
    can_assign_schedules: Optional[bool] = None
    access_profile_id: Optional[str] = None


class VisitorIn(BaseModel):
    name: str
    cedula: Optional[str] = None
    phone: Optional[str] = None
    is_minor: Optional[bool] = False


class VisitIn(BaseModel):
    type: str  # "personal" | "laboral"
    host_user_id: str
    scheduled_at: Optional[datetime] = None
    company_name: Optional[str] = None  # laboral only
    # Motivo — dropdown de catálogo (laboral). Valores válidos:
    #   reunion · capacitacion · visita_data_center · visita_centro_cableado · otra
    purpose: Optional[str] = None
    purpose_other: Optional[str] = None
    observations: Optional[str] = None  # max 300 caracteres
    visitors: List[VisitorIn]
    # Deprecados — se mantienen para retro-compatibilidad de datos históricos.
    motive: Optional[str] = None
    notes: Optional[str] = None


class VisitorPinIn(BaseModel):
    visitor_index: int
    pin: str


VISIT_PURPOSE_CATALOG = {
    "reunion": "Reunión",
    "capacitacion": "Capacitación",
    "visita_data_center": "Visita al Data Center",
    "visita_centro_cableado": "Visita al Centro de Cableado",
    "otra": "Otra",
}


class VisitSelfieIn(BaseModel):
    visitor_index: int
    selfie_base64: str


class UserPermissionsIn(BaseModel):
    can_create_visits: Optional[bool] = None
    can_view_visit_logs: Optional[bool] = None


class SelfieIn(BaseModel):
    selfie_base64: str
    face_descriptor: Optional[List[float]] = None


class PinIn(BaseModel):
    pin: str


class DepartmentIn(BaseModel):
    name: str
    description: Optional[str] = None


class SiteIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_meters: Optional[int] = None


class SiteResolveIn(BaseModel):
    link: str


class ScheduleBlock(BaseModel):
    start: str  # HH:MM
    end: str


class ScheduleIn(BaseModel):
    name: str
    blocks: List[ScheduleBlock]
    tolerance_minutes: int = 10
    justification_tolerance_minutes: int = 20
    site_id: Optional[str] = None


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    identification_method: Optional[Literal["face", "pin", "both"]] = None
    kiosk_enabled: Optional[bool] = None
    logo_base64: Optional[str] = None
    timezone: Optional[str] = None


class KioskUnlockIn(BaseModel):
    email: EmailStr
    password: str


class KioskFaceUnlockIn(BaseModel):
    face_descriptor: List[float]


class KioskPinIn(BaseModel):
    user_id: str
    pin: str


class KioskAttendanceIn(BaseModel):
    user_id: str
    type: Optional[Literal["in", "out", "auto"]] = "auto"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    site_id: Optional[str] = None
    selfie_base64: Optional[str] = None
    method: Optional[str] = "kiosk"


class AttendanceCheckIn(BaseModel):
    type: Literal["in", "out"]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    site_id: Optional[str] = None
    selfie_base64: Optional[str] = None


class JustifyIn(BaseModel):
    record_id: str
    justification: str


class JustifyDecideIn(BaseModel):
    record_id: str
    decision: Literal["approved", "rejected"]
    rejection_reason: Optional[str] = None


class NoveltyIn(BaseModel):
    type: Literal["vacation", "leave", "medical", "permission", "remote", "client_visit", "other"]
    start_date: str
    end_date: str
    start_time: Optional[str] = None  # HH:MM (no aplica a "vacation")
    end_time: Optional[str] = None    # HH:MM (no aplica a "vacation")
    reason: Optional[str] = None
    user_id: Optional[str] = None  # admin/supervisor can create for others


class NoveltyDecideIn(BaseModel):
    novelty_ids: List[str]
    decision: Literal["approved", "rejected"]
    comment: Optional[str] = None


class NoveltyPatchIn(BaseModel):
    """Payload para edición de novedad por parte del administrador.
    Todos los campos son opcionales — solo se actualizan los que se envían."""
    type: Optional[Literal["vacation", "leave", "medical", "permission", "remote", "client_visit", "other"]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[Literal["pending", "approved", "rejected"]] = None
    decision_comment: Optional[str] = None
    user_id: Optional[str] = None


# ------------------------------------------------------------------
# Startup: indexes + admin seed
# ------------------------------------------------------------------
@app.on_event("startup")
async def on_startup() -> None:
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.attendance.create_index([("user_id", 1), ("timestamp", -1)])
    await db.novelties.create_index([("user_id", 1), ("start_date", 1)])
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("user_id")
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)

    # Backfill: schedules sin ventana de justificación → default 20 min.
    await db.schedules.update_many(
        {"$or": [{"justification_tolerance_minutes": {"$exists": False}},
                 {"justification_tolerance_minutes": None}]},
        {"$set": {"justification_tolerance_minutes": 20}},
    )

    # Backfill: asistencia legacy sin justification_status.
    # - Con texto de justificación → 'approved' (mantiene comportamiento histórico).
    # - Sin texto → 'none'.
    await db.attendance.update_many(
        {"justification_status": {"$exists": False},
         "justification": {"$nin": [None, ""]}},
        {"$set": {"justification_status": "approved"}},
    )
    await db.attendance.update_many(
        {"justification_status": {"$exists": False}},
        {"$set": {"justification_status": "none"}},
    )

    # Backfill: recompute lateness for E2+ ("in" marca 2+ del día) usando la regla
    # del gap S1→E2 (>60 min). Recorre por (user_id, día) y arregla los registros
    # que fueron mal clasificados por la lógica antigua (que comparaba TODA entrada
    # contra blocks[0].start, inflando artificialmente late_minutes en E2+).
    await _backfill_entry_index_and_lateness()

    # Backfill: normaliza roles a las claves canónicas (admin/supervisor/employee)
    for alias, canonical in _ROLE_ALIASES.items():
        if alias == canonical:
            continue
        await db.users.update_many({"role": alias}, {"$set": {"role": canonical}})
    # Case variants (Empleado, Supervisor, Admin, etc.) normalizados por regex
    async for u in db.users.find({"role": {"$exists": True, "$ne": None}}, {"user_id": 1, "role": 1, "_id": 0}):
        canonical = normalize_role(u.get("role"))
        if u.get("role") != canonical:
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"role": canonical}})

    # Migración de datos: resolver department_id / site_id / schedule_id / supervisor_id
    # que estén guardados como NOMBRE (en lugar de ID interno). Esto ocurrió cuando
    # se importaban Excels con nombres antes de que existiera el resolver.
    dept_lookup, site_lookup, sched_lookup, sup_by_name, sup_by_email = await _load_import_lookups()
    async for u in db.users.find(
        {"$or": [
            {"department_id": {"$exists": True, "$ne": None, "$not": {"$regex": "^dept_"}}},
            {"site_id": {"$exists": True, "$ne": None, "$not": {"$regex": "^site_"}}},
            {"schedule_id": {"$exists": True, "$ne": None, "$not": {"$regex": "^sch_"}}},
            {"supervisor_id": {"$exists": True, "$ne": None, "$not": {"$regex": "^user_"}}},
        ]},
        {"user_id": 1, "department_id": 1, "site_id": 1, "schedule_id": 1,
         "supervisor_id": 1, "_id": 0},
    ):
        upd: Dict[str, Any] = {}
        d = (u.get("department_id") or "").strip()
        if d and not d.startswith("dept_"):
            m = dept_lookup.get(d.lower())
            if m:
                upd["department_id"] = m
        s = (u.get("site_id") or "").strip()
        if s and not s.startswith("site_"):
            m = site_lookup.get(s.lower())
            if m:
                upd["site_id"] = m
        sc = (u.get("schedule_id") or "").strip()
        if sc and not sc.startswith("sch_"):
            m = sched_lookup.get(sc.lower())
            if m:
                upd["schedule_id"] = m
        sup = (u.get("supervisor_id") or "").strip()
        if sup and not sup.startswith("user_"):
            m = sup_by_email.get(sup.lower()) if "@" in sup else sup_by_name.get(sup.lower())
            if m:
                upd["supervisor_id"] = m
        if upd:
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": upd})

    # Admin bootstrap (idempotent) — no toca hash existente si ya valida
    admin_email = os.environ.get("ADMIN_EMAIL", "").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        existing = await db.users.find_one({"email": admin_email})
        if existing is None:
            await db.users.insert_one({
                "user_id": new_id("user"),
                "email": admin_email,
                "name": "Administrator",
                "role": "admin",
                "password_hash": hash_password(admin_password),
                "password_updated_by_user": False,
                "onboarded": False,
                "created_at": now_utc(),
            })
            logger.info("Seed: admin '%s' creado.", admin_email)
        else:
            # Solo actualiza si la contraseña actual NO valida
            if not verify_password(admin_password, existing.get("password_hash", "")):
                await db.users.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"password_hash": hash_password(admin_password)}},
                )
                logger.info("Seed: contraseña admin refrescada.")

    # ------------------------------------------------------------------
    # Seed de usuarios Kiosco por sede (idempotente).
    # Uno por sede física — el admin puede rotar la contraseña después
    # y los reseeds NO la sobreescribirán.
    # ------------------------------------------------------------------
    await _seed_kiosk_users()
    # ------------------------------------------------------------------
    # Migración de rol legacy: supervisor → coordinador (idempotente).
    # ------------------------------------------------------------------
    await _migrate_supervisor_role_to_coordinador()
    # ------------------------------------------------------------------
    # Seed de perfiles de acceso del sistema (idempotente).
    # ------------------------------------------------------------------
    await _seed_access_profiles()
    logger.info("Startup completo.")


async def _find_site_by_keywords(*keywords: str) -> Optional[Dict[str, Any]]:
    """Busca una sede cuyo nombre contenga TODAS las palabras dadas
    (case-insensitive). Devuelve el doc de la sede o None."""
    async for s in db.sites.find({}, {"site_id": 1, "name": 1, "_id": 0}):
        name = (s.get("name") or "").lower()
        if all(k.lower() in name for k in keywords):
            return s
    return None


def _calculate_backfill_lateness(r: Dict[str, Any], in_idx: int, last_out_ts: Optional[datetime], blocks: list, tol_general: int, tol_justif: int):
    is_late, late_min, severity, req_just = False, 0, "on_time", False
    local_ts = r["timestamp"].astimezone(APP_TZ)
    if in_idx == 0:
        try:
            hh, mm = map(int, blocks[0]["start"].split(":"))
            expected = local_ts.replace(hour=hh, minute=mm, second=0, microsecond=0)
            delta = int((local_ts - expected).total_seconds() // 60)
            if delta > tol_general:
                is_late, late_min = True, delta
                if delta > (tol_general + tol_justif):
                    severity, req_just = "late_major", True
                else:
                    severity = "late_minor"
        except Exception:
            pass
    elif last_out_ts is not None:
        s1_local = last_out_ts.astimezone(APP_TZ)
        gap = int((local_ts - s1_local).total_seconds() // 60)
        if gap > 60:
            is_late, late_min = True, gap - 60
            if late_min > tol_justif:
                severity, req_just = "late_major", True
            else:
                severity = "late_minor"
    return is_late, late_min, severity, req_just


async def _backfill_entry_index_and_lateness() -> None:
    fixed = 0
    schedules_cache: Dict[str, Any] = {}

    async def _get_sched(sid: Optional[str]) -> Optional[Dict[str, Any]]:
        if not sid:
            return None
        if sid in schedules_cache:
            return schedules_cache[sid]
        s = await db.schedules.find_one({"schedule_id": sid})
        schedules_cache[sid] = s
        return s

    user_sched: Dict[str, Optional[str]] = {}
    async for u in db.users.find({}, {"user_id": 1, "schedule_id": 1, "_id": 0}):
        user_sched[u["user_id"]] = u.get("schedule_id")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    async for r in db.attendance.find(
        {},
        {"record_id": 1, "user_id": 1, "type": 1, "timestamp": 1,
         "is_late": 1, "late_minutes": 1, "late_severity": 1,
         "requires_justification": 1, "entry_index": 1,
         "justification_status": 1, "_id": 0},
    ).sort("timestamp", 1):
        ts = r.get("timestamp")
        if not isinstance(ts, datetime) or not r.get("record_id") or not r.get("user_id"):
            continue
        day = ts.astimezone(APP_TZ).strftime("%Y-%m-%d")
        grouped.setdefault(f"{r['user_id']}::{day}", []).append(r)

    for key, recs in grouped.items():
        uid, _ = key.split("::", 1)
        recs.sort(key=lambda x: x["timestamp"])
        in_idx = 0
        last_out_ts: Optional[datetime] = None
        sched = await _get_sched(user_sched.get(uid))
        blocks = (sched or {}).get("blocks") or []
        tol_general = int((sched or {}).get("tolerance_minutes", 10))
        tol_justif = int((sched or {}).get("justification_tolerance_minutes", 20))

        for r in recs:
            t = r.get("type")
            if t == "out":
                last_out_ts = r["timestamp"]
                continue
            if t != "in":
                continue

            is_late, late_min, severity, req_just = False, 0, "on_time", False
            if sched and blocks:
                is_late, late_min, severity, req_just = _calculate_backfill_lateness(
                    r, in_idx, last_out_ts, blocks, tol_general, tol_justif
                )

            jstatus = r.get("justification_status") or "none"
            if jstatus in ("approved", "rejected"):
                req_just = False

            new_vals = {
                "is_late": is_late,
                "late_minutes": late_min,
                "late_severity": severity,
                "requires_justification": req_just,
                "entry_index": in_idx,
            }
            if any(r.get(k) != v for k, v in new_vals.items()):
                await db.attendance.update_one({"record_id": r["record_id"]}, {"$set": new_vals})
                fixed += 1
            in_idx += 1

    if fixed:
        logger.info("Backfill: recomputadas tardanzas E1/E2 en %d registros.", fixed)




async def _seed_kiosk_users() -> None:
    """Crea los usuarios operativos del Kiosco:
        - Kiosco TBP  → asociado a "Sede Torre Banco Plaza"
        - Kiosco LCH  → asociado a "Sede Los Chaguaramos"
    Contraseña por defecto: 'Mega2026*' (override via KIOSK_TBP_PASSWORD /
    KIOSK_LCH_PASSWORD). El seed NO reescribe contraseñas ya cambiadas por
    el admin — sólo asegura que los usuarios existan con el site_id correcto.
    """
    default_pw = "Mega2026*"

    specs = [
        {
            "email": "kiosco.tbp@megasoft.com.ve",
            "name": "Kiosco TBP",
            "site_keywords": ("torre", "banco"),
            "password": os.environ.get("KIOSK_TBP_PASSWORD", default_pw),
        },
        {
            "email": "kiosco.lch@megasoft.com.ve",
            "name": "Kiosco LCH",
            "site_keywords": ("chaguaramos",),
            "password": os.environ.get("KIOSK_LCH_PASSWORD", default_pw),
        },
    ]

    for spec in specs:
        site = await _find_site_by_keywords(*spec["site_keywords"])
        if not site:
            logger.warning(
                "Seed kiosco: sede con palabras %s no encontrada; no se crea '%s'.",
                spec["site_keywords"], spec["email"],
            )
            continue

        existing = await db.users.find_one({"email": spec["email"]})
        if existing is None:
            await db.users.insert_one({
                "user_id": new_id("user"),
                "email": spec["email"],
                "name": spec["name"],
                "role": "kiosk",
                "site_id": site["site_id"],
                "password_hash": hash_password(spec["password"]),
                "onboarded": True,   # sin flujo de selfie
                "created_at": now_utc(),
            })
            logger.info("Seed kiosco: usuario '%s' creado (sede %s).",
                        spec["email"], site.get("name"))
        else:
            # Asegura role='kiosk' y site_id vigente. NO tocar el hash de la
            # contraseña si ya fue rotada por el admin.
            updates: Dict[str, Any] = {}
            if existing.get("role") != "kiosk":
                updates["role"] = "kiosk"
            if existing.get("site_id") != site["site_id"]:
                updates["site_id"] = site["site_id"]
            if updates:
                await db.users.update_one({"_id": existing["_id"]}, {"$set": updates})
                logger.info("Seed kiosco: '%s' actualizado (%s).",
                            spec["email"], list(updates.keys()))


async def _seed_access_profiles() -> None:
    """Crea los 4 perfiles de sistema (Administrador, Coordinador, Gerente,
    Empleado) si no existen. Idempotente. Los perfiles de sistema no se pueden
    borrar, pero sí editar. Los defaults corresponden a la jerarquía típica —
    el admin puede afinar cada uno luego."""
    def _pset(keys):
        return {k: (k in keys) for k in MENU_KEYS}

    specs = [
        (
            "Administrador",
            "Acceso total al sistema.",
            {k: True for k in MENU_KEYS},
        ),
        (
            "Director",
            "Vista ejecutiva: dashboard, matriz, novedades, reportes.",
            _pset({
                "mi_carnet", "historial", "dashboard", "matriz",
                "novedades", "equipo", "reportes", "visitas_agendar",
                "visitas_historico",
            }),
        ),
        (
            "Gerente",
            "Gestión de equipo, horarios y reportes.",
            _pset({
                "mi_carnet", "historial", "dashboard", "matriz",
                "novedades", "equipo", "horarios", "asignar_horarios",
                "reportes", "visitas_agendar", "visitas_historico",
            }),
        ),
        (
            "Coordinador",
            "Gestión del equipo directo, matriz y novedades.",
            _pset({
                "mi_carnet", "historial", "matriz", "novedades", "equipo",
                "dashboard", "visitas_agendar", "visitas_historico",
            }),
        ),
        (
            "Empleado",
            "Autoservicio: carnet, historial y agendar visitas.",
            _pset({"mi_carnet", "historial", "visitas_agendar"}),
        ),
    ]

    # Migración legacy: si existía "Supervisor" (nombre anterior), lo dejamos
    # tal cual — el admin puede eliminarlo. NO lo renombramos automáticamente
    # para no borrar customizaciones que ya haya hecho.
    for name, desc, perms in specs:
        existing = await db.access_profiles.find_one({"name": name})
        if existing:
            continue
        doc = {
            "profile_id": new_id("prof"),
            "name": name,
            "description": desc,
            "permissions": perms,
            "is_system": True,
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        await db.access_profiles.insert_one(doc)
        logger.info("Seed perfil de acceso: '%s' creado.", name)


async def _migrate_supervisor_role_to_coordinador() -> None:
    """Migración idempotente Feb 2026: renombra rol legacy 'supervisor' a
    'coordinador' en la colección users. Ejecutable en cada startup sin efecto."""
    res = await db.users.update_many(
        {"role": "supervisor"},
        {"$set": {"role": "coordinador"}},
    )
    if res.modified_count:
        logger.info(
            "Migración: %s usuarios reperfilados de 'supervisor' → 'coordinador'.",
            res.modified_count,
        )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    client.close()


# ==================================================================
# ROOT / HEALTH
# ==================================================================
@api.get("/")
async def root() -> Dict[str, Any]:
    return {"service": "megasoft-asistencia", "status": "ok", "time": now_utc().isoformat()}


# ==================================================================
# AUTH · RBAC (ACCESS PROFILES) — migrados a routes/auth.py y routes/access_profiles.py
# (Fase A · Iteración 3, feb-2026).
# ==================================================================
def _parse_date_range(from_date: Optional[str], to_date: Optional[str]) -> Optional[Dict[str, Any]]:
    if not from_date and not to_date:
        return None
    rng: Dict[str, Any] = {}
    try:
        if from_date:
            rng["$gte"] = datetime.fromisoformat(from_date).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
        if to_date:
            rng["$lt"] = (datetime.fromisoformat(to_date).replace(tzinfo=APP_TZ)
                          + timedelta(days=1)).astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido (usa YYYY-MM-DD)")
    return rng


# ==================================================================
# USERS · IMPORT — migrados a routes/users.py
# (Fase A · Iteración 4, feb-2026).
# `_load_import_lookups` se mantiene aquí porque el hook on_startup lo usa
# para normalizar departments/sites/schedules/supervisor guardados por nombre.
# ==================================================================

async def _load_import_lookups() -> tuple:
    """Devuelve 5 diccionarios lower-keyed para resolver nombres → IDs."""
    dept_map: Dict[str, str] = {}
    site_map: Dict[str, str] = {}
    sched_map: Dict[str, str] = {}
    sup_by_name: Dict[str, str] = {}
    sup_by_email: Dict[str, str] = {}
    async for d in db.departments.find({}, {"department_id": 1, "name": 1, "_id": 0}):
        if d.get("name"):
            dept_map[d["name"].strip().lower()] = d["department_id"]
    async for s in db.sites.find({}, {"site_id": 1, "name": 1, "_id": 0}):
        if s.get("name"):
            site_map[s["name"].strip().lower()] = s["site_id"]
    async for s in db.schedules.find({}, {"schedule_id": 1, "name": 1, "_id": 0}):
        if s.get("name"):
            sched_map[s["name"].strip().lower()] = s["schedule_id"]
    async for u in db.users.find({"role": {"$in": list(LEADER_OR_ADMIN_ROLES)}},
                                 {"user_id": 1, "name": 1, "email": 1, "_id": 0}):
        if u.get("name"):
            sup_by_name[u["name"].strip().lower()] = u["user_id"]
        if u.get("email"):
            sup_by_email[u["email"].strip().lower()] = u["user_id"]
    return dept_map, site_map, sched_map, sup_by_name, sup_by_email




# ==================================================================
# SETTINGS (2 endpoints)
# ==================================================================
# ==================================================================
# SETTINGS · SITES · DEPARTMENTS · DOCS — migrados a routes/catalogs.py
# (Fase A · Iteración 3, feb-2026).
# ==================================================================


# ==================================================================
# SCHEDULES · ASSIGNMENTS · PLANS — migrados a routes/schedules.py
# (Fase A · Iteración 3, feb-2026).
# ==================================================================


# ==================================================================
# KIOSK · BACKUP · ONBOARDING — migrados a routes/kiosk.py y routes/admin.py
# (Fase A · Iteración 3, feb-2026).
# ==================================================================

# ------------------------------------------------------------------
# Wire router + CORS
# ------------------------------------------------------------------
# Importar los módulos de routes registra sus endpoints en `api` via side-effect
# (cada archivo hace @api.get/post/... al ser cargado). Debe ir ANTES de
# app.include_router(api) para que las rutas nuevas se incluyan.
# Refactor Fase A · Iteración 4 (feb-2026):
#   - attendance + novelties + visits + reports + matrix (iter 1-2)
#   - auth + catalogs + access_profiles + schedules + kiosk + admin (iter 3)
#   - users (iter 4 — cierra Fase A · server.py < 1000 líneas)
from routes import (  # noqa: F401,E402
    attendance, novelties, visits, reports, matrix,
    auth, catalogs, access_profiles, schedules, kiosk, admin,
    users,
)

app.include_router(api)

# CORS estricto (feb-2026): sólo aceptar orígenes explícitos declarados en la
# variable `CORS_ORIGINS`. Si la variable está vacía, se usan los dominios
# conocidos de Emergent (producción + preview) para no depender del `.env`
# de producción. En producción, para agregar otro dominio, exportar
# `CORS_ORIGINS="dom1,dom2,..."` en las variables de entorno del deploy.
_DEFAULT_CORS_ORIGINS = [
    "https://asistencia-web-1.emergent.host",
    "https://asistencia-web-1.preview.emergentagent.com",
]
_cors_raw = os.environ.get("CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = _DEFAULT_CORS_ORIGINS
    logger.info("CORS_ORIGINS no definido; usando defaults: %s", _cors_origins)
elif _cors_origins == ["*"]:
    logger.warning("CORS_ORIGINS='*' — configuración insegura en producción.")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
