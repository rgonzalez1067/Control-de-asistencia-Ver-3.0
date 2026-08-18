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
MENU_CATALOG: List[Dict[str, Any]] = [
    # Sección: Personal
    {"key": "mi_carnet",          "label": "Mi carnet",          "section": "Personal"},
    {"key": "historial",          "label": "Historial personal", "section": "Personal"},
    # Sección: Operación
    {"key": "kiosco_activar",     "label": "Activar Kiosco",     "section": "Operación"},
    {"key": "matriz",             "label": "Reporte matricial",  "section": "Operación"},
    {"key": "novedades",          "label": "Novedades",          "section": "Operación"},
    {"key": "equipo",             "label": "Mi equipo",          "section": "Operación"},
    {"key": "dashboard",          "label": "Dashboard",          "section": "Operación"},
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


async def _backfill_entry_index_and_lateness() -> None:
    """Recalcula ``entry_index`` y la clasificación de tardanza para todos los
    registros de asistencia ``type == "in"``:

    - **E1** (primera entrada del día): fórmula clásica → ``delta`` respecto a
      ``blocks[0].start + tolerance``.
    - **E2+**: fórmula de gap → sólo se penaliza el exceso sobre 60 min entre
      la primera salida S1 y la segunda entrada E2. Sin S1 previo no se marca
      como tarde (el registro se considera "fuera de patrón").

    Es idempotente: sólo escribe los campos si difieren de los actuales.
    Se ejecuta una única vez tras el startup (rápido: agrupa por user_id+día).
    """
    schedules_cache: Dict[str, Any] = {}

    async def _get_sched(sid: Optional[str]) -> Optional[Dict[str, Any]]:
        if not sid:
            return None
        if sid in schedules_cache:
            return schedules_cache[sid]
        s = await db.schedules.find_one({"schedule_id": sid})
        schedules_cache[sid] = s
        return s

    # Traer usuarios con su schedule_id (para consultar rápido)
    user_sched: Dict[str, Optional[str]] = {}
    async for u in db.users.find({}, {"user_id": 1, "schedule_id": 1, "_id": 0}):
        user_sched[u["user_id"]] = u.get("schedule_id")

    # Agrupamos por user_id+día — traemos TODO ordenado por timestamp
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    async for r in db.attendance.find(
        {},
        {"record_id": 1, "user_id": 1, "type": 1, "timestamp": 1,
         "is_late": 1, "late_minutes": 1, "late_severity": 1,
         "requires_justification": 1, "entry_index": 1,
         "justification_status": 1, "_id": 0},
    ).sort("timestamp", 1):
        ts = r.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        if not r.get("record_id") or not r.get("user_id"):
            continue
        day = ts.astimezone(APP_TZ).strftime("%Y-%m-%d")
        key = f"{r['user_id']}::{day}"
        grouped.setdefault(key, []).append(r)

    fixed = 0
    for key, recs in grouped.items():
        uid, day = key.split("::", 1)
        # Ordenados por timestamp asc
        recs.sort(key=lambda x: x["timestamp"])
        # Índice de "in"
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

            # Recalcular clasificación
            is_late, late_min = False, 0
            severity = "on_time"
            req_just = False

            if sched and blocks:
                local_ts = r["timestamp"].astimezone(APP_TZ)
                if in_idx == 0:
                    # E1
                    try:
                        hh, mm = map(int, blocks[0]["start"].split(":"))
                        expected = local_ts.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        delta = int((local_ts - expected).total_seconds() // 60)
                        if delta > tol_general:
                            is_late = True
                            late_min = delta
                            if delta > (tol_general + tol_justif):
                                severity = "late_major"
                                req_just = True
                            else:
                                severity = "late_minor"
                    except Exception:
                        pass
                else:
                    # E2+
                    if last_out_ts is not None:
                        s1_local = last_out_ts.astimezone(APP_TZ)
                        gap = int((local_ts - s1_local).total_seconds() // 60)
                        if gap > 60:
                            is_late = True
                            late_min = gap - 60
                            if late_min > tol_justif:
                                severity = "late_major"
                                req_just = True
                            else:
                                severity = "late_minor"

            # Preservar decisiones ya tomadas por el supervisor:
            # si hay un status distinto de "none"/"pending" NO forzamos requires_justification.
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
            old_vals = {k: r.get(k) for k in new_vals.keys()}
            if old_vals != new_vals:
                await db.attendance.update_one(
                    {"record_id": r["record_id"]},
                    {"$set": new_vals},
                )
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
# USERS (8 endpoints)
# ==================================================================
@api.get("/users")
async def users_list(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if user.get("role") in LEADER_ROLES:
        q["user_id"] = {"$in": await supervisor_scope_ids(user)}
    docs = await db.users.find(q, {"password_hash": 0, "pin_code_hash": 0,
                                    "selfie_base64": 0, "face_descriptor": 0}).to_list(1000)
    for d in docs:
        strip_mongo_id(d)
    return docs


@api.post("/users")
async def users_create(payload: UserIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email ya registrado")
    doc = payload.model_dump(exclude_none=True)
    doc["email"] = email
    doc["user_id"] = new_id("user")
    doc["onboarded"] = False
    doc["created_at"] = now_utc()
    if payload.password:
        doc["password_hash"] = hash_password(payload.password)
        doc.pop("password", None)
    if payload.pin:
        if not payload.pin.isdigit() or not (4 <= len(payload.pin) <= 8):
            raise HTTPException(status_code=400, detail="PIN debe ser 4-8 dígitos")
        doc["pin_code_hash"] = hash_password(payload.pin)
        doc.pop("pin", None)
    await db.users.insert_one(doc)
    return sanitize_user(doc)


@api.get("/users/{user_id}")
async def users_get(user_id: str,
                    _: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    u = await db.users.find_one({"user_id": user_id},
                                {"password_hash": 0, "pin_code_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    strip_mongo_id(u)
    return u


@api.put("/users/{user_id}")
async def users_update(user_id: str, payload: UserUpdate,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    # `exclude_unset=True` respeta la diferencia entre "campo omitido" (no cambia)
    # y "campo enviado con null" (desasignar). Esto permite que el admin ponga
    # `schedule_id`/`department_id`/`site_id`/`supervisor_id` en "Sin asignar".
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Sin cambios")
    res = await db.users.update_one({"user_id": user_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u = await db.users.find_one({"user_id": user_id},
                                {"password_hash": 0, "pin_code_hash": 0})
    return strip_mongo_id(u)


@api.delete("/users/{user_id}")
async def users_delete(user_id: str,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.users.delete_one({"user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


@api.post("/users/{user_id}/selfie")
async def users_selfie(user_id: str, payload: SelfieIn,
                       user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    if user["user_id"] != user_id and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="No autorizado")
    updates = {"selfie_base64": payload.selfie_base64, "onboarded": True}
    if payload.face_descriptor is not None:
        updates["face_descriptor"] = payload.face_descriptor
    res = await db.users.update_one({"user_id": user_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


@api.post("/users/{user_id}/pin")
async def users_set_pin(user_id: str, payload: PinIn,
                        user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    if user["user_id"] != user_id and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="No autorizado")
    if not payload.pin.isdigit() or not (4 <= len(payload.pin) <= 8):
        raise HTTPException(status_code=400, detail="PIN debe ser 4-8 dígitos")
    await db.users.update_one({"user_id": user_id},
                              {"$set": {"pin_code_hash": hash_password(payload.pin)}})
    return {"ok": True}


@api.get("/users/{user_id}/photo")
async def users_get_photo(user_id: str,
                          _: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    u = await db.users.find_one({"user_id": user_id},
                                {"selfie_base64": 1, "onboarded": 1, "name": 1, "_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {
        "user_id": user_id,
        "name": u.get("name"),
        "onboarded": u.get("onboarded", False),
        "selfie_base64": u.get("selfie_base64"),
    }


@api.get("/users/import/template")
async def users_import_template(_: Dict[str, Any] = Depends(require_roles("admin"))) -> StreamingResponse:
    """Genera un Excel .xlsx con 2 pestañas:
       • Empleados  → cabeceras vacías, listas para llenar
       • Ejemplos   → filas de referencia con casos típicos
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()

    headers = [
        "email", "name", "cedula", "role", "position",
        "department_id", "site_id", "supervisor_id", "schedule_id",
        "password", "kiosk_pin",
    ]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_align = Alignment(horizontal="center", vertical="center")

    ws1 = wb.active
    ws1.title = "Empleados"
    ws1.append(headers)
    for i, _c in enumerate(headers, start=1):
        cell = ws1.cell(row=1, column=i)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws1.column_dimensions[cell.column_letter].width = max(14, len(_c) + 4)
    ws1.freeze_panes = "A2"

    ws2 = wb.create_sheet("Ejemplos")
    ws2.append(headers)
    for i, _c in enumerate(headers, start=1):
        cell = ws2.cell(row=1, column=i)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws2.column_dimensions[cell.column_letter].width = max(14, len(_c) + 4)
    ws2.freeze_panes = "A2"

    ejemplos = [
        ["jperez@empresa.com", "Juan Pérez", "12345678", "employee",
         "Analista", "Ventas Pyme", "Sede Torre Banco Plaza", "atata@empresa.com", "Día Completo", "Temporal2026*", "1234"],
        ["mrodriguez@empresa.com", "María Rodríguez", "23456789", "Supervisor",
         "Coordinadora", "Recursos Humanos", "Sede Torre Banco Plaza", "", "Día Completo", "", "5678"],
        ["cgomez@empresa.com", "Carlos Gómez", "34567890", "employee",
         "Técnico Soporte", "Soporte y Monitoreo", "Sede Los Chaguaramos", "María Rodríguez", "Turno Uno", "", ""],
    ]
    for row in ejemplos:
        ws2.append(row)

    # Nota / leyenda al pie de la pestaña Ejemplos
    ws2.append([])
    ws2.append(["NOTAS:"])
    ws2["A" + str(ws2.max_row)].font = Font(bold=True, color="B45309")
    notas = [
        "• Sólo email y name son obligatorios. El resto puede ir vacío.",
        "• role: employee | supervisor | admin (acepta 'Empleado', 'Supervisor', 'Administrador').",
        "• department_id / site_id / schedule_id: puedes escribir el NOMBRE tal como aparece en el sistema (ej. 'Ventas Pyme', 'Sede Torre Banco Plaza', 'Día Completo') o el ID interno (dept_xxx / site_xxx / sch_xxx).",
        "• supervisor_id: acepta el email del supervisor (ej. 'atata@empresa.com'), su nombre completo tal cual está registrado, o el ID interno user_xxx.",
        "• Si el email ya existe → se ACTUALIZAN sólo los campos con valor (no sobrescribe con vacío).",
        "• Si el email NO existe → se INSERTA un nuevo empleado.",
        "• password: sólo se aplica al crear. Si se omite, se genera uno aleatorio.",
        "• kiosk_pin: 4 dígitos numéricos para el modo kiosco (marca con PIN).",
        "• Cualquier NOMBRE que no exista en el sistema aparecerá en la pestaña 'Errores' del preview y NO se guardará.",
    ]
    for n in notas:
        ws2.append([n])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=users_template.xlsx"},
    )


@api.post("/users/import/preview")
async def users_import_preview(file: UploadFile = File(...),
                               _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Analiza el Excel sin escribir en BD. Retorna qué filas se crearían,
       cuáles se actualizarían (con los campos que cambiarían) y los errores."""
    from openpyxl import load_workbook
    raw = await file.read()
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Archivo Excel inválido: {e}") from None
    ws = wb["Empleados"] if "Empleados" in wb.sheetnames else wb.active

    rows = ws.iter_rows(values_only=True)
    try:
        headers_row = next(rows)
    except StopIteration:
        raise HTTPException(status_code=400, detail="La hoja está vacía") from None
    headers = [(str(h).strip().lower() if h is not None else "") for h in headers_row]
    if not {"email", "name"}.issubset(set(headers)):
        raise HTTPException(status_code=400, detail="Faltan columnas obligatorias: email, name")

    def _get(row, key):
        try:
            idx = headers.index(key)
        except ValueError:
            return None
        if idx >= len(row):
            return None
        val = row[idx]
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None

    # Lookup tables (name → id, y email → user_id para supervisores)
    dept_map, site_map, sched_map, sup_by_name, sup_by_email = await _load_import_lookups()

    def _resolve(kind: str, value: Optional[str], row_num: int, errors: list) -> Optional[str]:
        """Convierte un valor de Excel a un ID válido. Acepta el ID literal
        o el nombre. Devuelve None si el valor no se puede resolver."""
        if value is None:
            return None
        raw_val = str(value).strip()
        if not raw_val:
            return None
        low = raw_val.lower()
        if kind == "department":
            if raw_val.startswith("dept_"):
                return raw_val
            match = dept_map.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Departamento no encontrado: {raw_val!r}"})
            return match
        if kind == "site":
            if raw_val.startswith("site_"):
                return raw_val
            match = site_map.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Sede no encontrada: {raw_val!r}"})
            return match
        if kind == "schedule":
            if raw_val.startswith("sch_"):
                return raw_val
            match = sched_map.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Horario no encontrado: {raw_val!r}"})
            return match
        if kind == "supervisor":
            if raw_val.startswith("user_"):
                return raw_val
            # Trata como email primero, luego como nombre
            if "@" in raw_val:
                match = sup_by_email.get(low)
            else:
                match = sup_by_name.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Supervisor no encontrado: {raw_val!r}"})
            return match
        return raw_val

    to_create: List[Dict[str, Any]] = []
    to_update: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for i, row in enumerate(rows, start=2):
        if row is None or all(v is None for v in row):
            continue
        email = (_get(row, "email") or "").lower()
        name = _get(row, "name")
        if not email or not name:
            errors.append({"row": i, "email": email or None, "reason": "email/name requerido"})
            continue

        candidate = {
            "email": email,
            "name": name,
            "cedula": _get(row, "cedula"),
            "role": normalize_role(_get(row, "role")),
            "position": _get(row, "position"),
            "department_id": _resolve("department", _get(row, "department_id"), i, errors),
            "site_id": _resolve("site", _get(row, "site_id"), i, errors),
            "supervisor_id": _resolve("supervisor", _get(row, "supervisor_id"), i, errors),
            "schedule_id": _resolve("schedule", _get(row, "schedule_id"), i, errors),
            "kiosk_pin": _get(row, "kiosk_pin"),
        }
        existing = await db.users.find_one({"email": email})
        if not existing:
            to_create.append({"row": i, **candidate,
                              "role": candidate["role"] or "employee"})
        else:
            # Calcula qué campos cambiarían (case-sensitive: ideal para detectar
            # cambios de mayúsculas/minúsculas en el nombre).
            changes = {}
            for k, v in candidate.items():
                if v is None:
                    continue
                if str(existing.get(k) or "") != str(v):
                    changes[k] = {"from": existing.get(k), "to": v}
            # Todo registro existente se marca para actualizar (aunque no haya diffs)
            # porque siempre reescribimos el "name" para garantizar mayúsculas.
            to_update.append({
                "row": i, "email": email, "name": name,
                "changes": changes,
                "will_force_name": not changes,   # marca informativa
            })

    return {
        "total_rows": len(to_create) + len(to_update) + len(errors),
        "to_create": to_create,
        "to_update": to_update,
        "errors": errors,
    }


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


@api.post("/users/import")
async def users_import(file: UploadFile = File(...),
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Importa empleados desde Excel (.xlsx). Upsert por email:
       • Si email no existe → INSERT
       • Si email existe    → UPDATE sólo de campos con valor (los vacíos no borran datos)
    """
    from openpyxl import load_workbook
    raw = await file.read()
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Archivo Excel inválido: {e}") from None

    if "Empleados" in wb.sheetnames:
        ws = wb["Empleados"]
    else:
        ws = wb.active

    rows = ws.iter_rows(values_only=True)
    try:
        headers_row = next(rows)
    except StopIteration:
        raise HTTPException(status_code=400, detail="La hoja está vacía") from None

    headers = [(str(h).strip().lower() if h is not None else "") for h in headers_row]
    required = {"email", "name"}
    if not required.issubset(set(headers)):
        raise HTTPException(status_code=400, detail="Faltan columnas obligatorias: email, name")

    def _get(row, key):
        try:
            idx = headers.index(key)
        except ValueError:
            return None
        if idx >= len(row):
            return None
        val = row[idx]
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None

    created, updated, errors = 0, 0, []
    created_list: List[str] = []
    updated_list: List[str] = []
    dept_map, site_map, sched_map, sup_by_name, sup_by_email = await _load_import_lookups()

    def _resolve_ref(kind: str, value: Optional[str], row_num: int) -> Optional[str]:
        if value is None:
            return None
        raw_val = str(value).strip()
        if not raw_val:
            return None
        low = raw_val.lower()
        if kind == "department":
            if raw_val.startswith("dept_"):
                return raw_val
            match = dept_map.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Departamento no encontrado: {raw_val!r}"})
            return match
        if kind == "site":
            if raw_val.startswith("site_"):
                return raw_val
            match = site_map.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Sede no encontrada: {raw_val!r}"})
            return match
        if kind == "schedule":
            if raw_val.startswith("sch_"):
                return raw_val
            match = sched_map.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Horario no encontrado: {raw_val!r}"})
            return match
        if kind == "supervisor":
            if raw_val.startswith("user_"):
                return raw_val
            match = sup_by_email.get(low) if "@" in raw_val else sup_by_name.get(low)
            if not match:
                errors.append({"row": row_num, "email": None,
                               "reason": f"Supervisor no encontrado: {raw_val!r}"})
            return match
        return raw_val

    for i, row in enumerate(rows, start=2):
        if row is None or all(v is None for v in row):
            continue
        try:
            email = (_get(row, "email") or "").lower()
            name = _get(row, "name")
            if not email or not name:
                errors.append({"row": i, "email": email or None, "reason": "email/name requerido"})
                continue

            payload_fields = {
                "cedula": _get(row, "cedula"),
                "role": normalize_role(_get(row, "role")) if _get(row, "role") else None,
                "position": _get(row, "position"),
                "department_id": _resolve_ref("department", _get(row, "department_id"), i),
                "site_id": _resolve_ref("site", _get(row, "site_id"), i),
                "supervisor_id": _resolve_ref("supervisor", _get(row, "supervisor_id"), i),
                "schedule_id": _resolve_ref("schedule", _get(row, "schedule_id"), i),
                "kiosk_pin": _get(row, "kiosk_pin"),
            }
            # Descartamos None para no sobreescribir con vacío en updates.
            set_fields = {k: v for k, v in payload_fields.items() if v is not None}
            # name siempre lo actualizamos si el email ya existe
            set_fields["name"] = name

            existing = await db.users.find_one({"email": email})
            if existing:
                if set_fields:
                    await db.users.update_one({"email": email}, {"$set": set_fields})
                updated += 1
                updated_list.append(email)
            else:
                pw = _get(row, "password") or secrets.token_urlsafe(8)
                doc = {
                    "user_id": new_id("user"),
                    "email": email,
                    "name": name,
                    "cedula": payload_fields.get("cedula"),
                    "role": payload_fields.get("role") or "employee",
                    "position": payload_fields.get("position"),
                    "department_id": payload_fields.get("department_id"),
                    "site_id": payload_fields.get("site_id"),
                    "supervisor_id": payload_fields.get("supervisor_id"),
                    "schedule_id": payload_fields.get("schedule_id"),
                    "kiosk_pin": payload_fields.get("kiosk_pin"),
                    "onboarded": False,
                    "created_at": now_utc(),
                    "password_hash": hash_password(pw),
                }
                await db.users.insert_one(doc)
                created += 1
                created_list.append(email)
        except Exception as e:  # noqa: BLE001
            errors.append({"row": i, "email": None, "reason": str(e)})
    return {
        "created": created,
        "updated": updated,
        "created_emails": created_list,
        "updated_emails": updated_list,
        "errors": errors,
    }


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
# Refactor Fase A · Iteración 3 (feb-2026):
#   - attendance + novelties + visits + reports + matrix (iter 1-2)
#   - auth + catalogs + access_profiles + schedules + kiosk + admin (iter 3)
from routes import (  # noqa: F401,E402
    attendance, novelties, visits, reports, matrix,
    auth, catalogs, access_profiles, schedules, kiosk, admin,
)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
