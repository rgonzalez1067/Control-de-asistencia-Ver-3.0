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
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
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
# AUTH (7 endpoints)
# ==================================================================
@api.get("/auth/needs-bootstrap")
async def auth_needs_bootstrap() -> Dict[str, bool]:
    """True si no existe ningún usuario admin (para primer setup)."""
    admin = await db.users.find_one({"role": "admin"})
    return {"needs_bootstrap": admin is None}


@api.post("/auth/register")
async def auth_register(payload: RegisterIn, response: Response) -> Dict[str, Any]:
    admin_exists = await db.users.find_one({"role": "admin"})
    # Sólo permitir registro público si aún no hay admin (bootstrap del primer admin)
    if admin_exists is not None:
        raise HTTPException(status_code=403, detail="Registro público deshabilitado")
    email = payload.email.lower().strip()
    exists = await db.users.find_one({"email": email})
    if exists:
        raise HTTPException(status_code=409, detail="Email ya registrado")
    user = {
        "user_id": new_id("user"),
        "email": email,
        "name": payload.name,
        "role": "admin",  # el primero es admin
        "cedula": payload.cedula,
        "password_hash": hash_password(payload.password),
        "onboarded": False,
        "created_at": now_utc(),
    }
    await db.users.insert_one(user)
    token = create_access_token(user["user_id"], user["role"])
    return {"token": token, "user": await enrich_user_with_permissions(user)}


@api.post("/auth/login")
async def auth_login(payload: LoginIn, response: Response) -> Dict[str, Any]:
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_access_token(user["user_id"], user["role"])
    return {"token": token, "user": await enrich_user_with_permissions(user)}


@api.get("/auth/me")
async def auth_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return await enrich_user_with_permissions(user)


@api.post("/auth/logout")
async def auth_logout(response: Response) -> Dict[str, bool]:
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


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


@api.post("/auth/change-password")
async def auth_change_password(payload: ChangePasswordIn,
                               user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    if not verify_password(payload.old_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta a la actual")
    validate_password_policy(payload.new_password)
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"password_hash": hash_password(payload.new_password),
                                        "password_updated_at": now_utc(),
                                        "must_change_password": False}})
    return {"ok": True}


@api.post("/auth/change-pin")
async def auth_change_pin(payload: ChangePinIn,
                          user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    """Autoservicio: el usuario cambia su PIN de marcaje presentando su
    contraseña actual. El PIN se guarda hasheado (nunca en texto plano)."""
    if not verify_password(payload.current_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    if not payload.new_pin.isdigit():
        raise HTTPException(status_code=400, detail="El PIN debe ser numérico")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"pin_code_hash": hash_password(payload.new_pin),
                  "pin_updated_at": now_utc()}},
    )
    return {"ok": True}


# ---------------------------------------------------------------------
# RBAC — Access Profiles CRUD
# ---------------------------------------------------------------------
def _access_profile_to_public(p: Dict[str, Any]) -> Dict[str, Any]:
    p = strip_mongo_id(dict(p))
    # Devuelve el diccionario completo incluyendo TODAS las claves del catálogo
    # (default False para las no presentes) — así el frontend no tiene que
    # decidir qué falta.
    perms = p.get("permissions", {}) or {}
    p["permissions"] = {k: bool(perms.get(k, False)) for k in MENU_KEYS}
    return p


@api.get("/access-profiles/catalog")
async def access_profiles_catalog(_: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Catálogo canónico de opciones que se pueden gobernar por perfil."""
    return {"items": MENU_CATALOG, "keys": MENU_KEYS}


@api.get("/access-profiles")
async def access_profiles_list(_: Dict[str, Any] = Depends(require_roles("admin"))) -> List[Dict[str, Any]]:
    docs = await db.access_profiles.find({}).sort("name", 1).to_list(1000)
    return [_access_profile_to_public(d) for d in docs]


@api.post("/access-profiles")
async def access_profiles_create(payload: AccessProfileIn,
                                 _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    if await db.access_profiles.find_one({"name": payload.name.strip()}):
        raise HTTPException(status_code=409, detail=f"Ya existe un perfil con el nombre '{payload.name}'")
    doc = {
        "profile_id": new_id("prof"),
        "name": payload.name.strip(),
        "description": (payload.description or "").strip() or None,
        "permissions": {k: bool(payload.permissions.get(k, False)) for k in MENU_KEYS},
        "is_system": False,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.access_profiles.insert_one(doc)
    return _access_profile_to_public(doc)


@api.put("/access-profiles/{profile_id}")
async def access_profiles_update(profile_id: str, payload: AccessProfileIn,
                                 _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    existing = await db.access_profiles.find_one({"profile_id": profile_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    # Nombres únicos (case-insensitive, excluyendo el propio)
    dupe = await db.access_profiles.find_one({
        "name": {"$regex": f"^{payload.name.strip()}$", "$options": "i"},
        "profile_id": {"$ne": profile_id},
    })
    if dupe:
        raise HTTPException(status_code=409, detail=f"Ya existe otro perfil con el nombre '{payload.name}'")
    updates = {
        "name": payload.name.strip(),
        "description": (payload.description or "").strip() or None,
        "permissions": {k: bool(payload.permissions.get(k, False)) for k in MENU_KEYS},
        "updated_at": now_utc(),
    }
    await db.access_profiles.update_one({"profile_id": profile_id}, {"$set": updates})
    doc = await db.access_profiles.find_one({"profile_id": profile_id})
    return _access_profile_to_public(doc)


@api.delete("/access-profiles/{profile_id}")
async def access_profiles_delete(profile_id: str,
                                 _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    prof = await db.access_profiles.find_one({"profile_id": profile_id})
    if not prof:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    if prof.get("is_system"):
        raise HTTPException(status_code=400, detail="Los perfiles del sistema no se pueden eliminar")
    # Al eliminar, se desasigna de cualquier usuario que lo tuviera.
    in_use = await db.users.count_documents({"access_profile_id": profile_id})
    if in_use:
        await db.users.update_many(
            {"access_profile_id": profile_id},
            {"$set": {"access_profile_id": None}},
        )
    await db.access_profiles.delete_one({"profile_id": profile_id})
    return {"ok": True}


@api.put("/users/{user_id}/access-profile")
async def user_set_access_profile(user_id: str, payload: AssignProfileIn,
                                  _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    if payload.profile_id:
        prof = await db.access_profiles.find_one({"profile_id": payload.profile_id})
        if not prof:
            raise HTTPException(status_code=404, detail="Perfil no encontrado")
    res = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"access_profile_id": payload.profile_id}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True, "user_id": user_id, "profile_id": payload.profile_id}


@api.post("/access-profiles/assign-department")
async def access_profile_assign_department(payload: AssignProfileToDeptIn,
                                           _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Aplica un perfil a TODOS los usuarios de un departamento en batch."""
    if payload.profile_id:
        prof = await db.access_profiles.find_one({"profile_id": payload.profile_id})
        if not prof:
            raise HTTPException(status_code=404, detail="Perfil no encontrado")
    # Excluye admin/kiosk del re-perfilado — los admin nunca pierden acceso
    # y los kiosk-users no usan sidebar.
    q = {
        "department_id": payload.department_id,
        "role": {"$nin": ["admin", "kiosk"]},
    }
    res = await db.users.update_many(q, {"$set": {"access_profile_id": payload.profile_id}})
    return {"ok": True, "matched": res.matched_count, "modified": res.modified_count}


@api.post("/auth/reset-password")
async def auth_reset_password(payload: ResetPasswordIn,
                              _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.users.update_one(
        {"user_id": payload.user_id},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "must_change_password": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


@api.post("/admin/reset-all-passwords")
async def admin_reset_all_passwords(
    payload: Dict[str, Any],
    _: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, Any]:
    """Resetea la contraseña de TODOS los usuarios no-admin al valor indicado y
    marca `must_change_password=true` para forzar cambio al primer login.
    Payload: {"new_password": "Mega2026*"}"""
    new_password = (payload or {}).get("new_password")
    if not new_password:
        raise HTTPException(status_code=400, detail="Falta new_password")
    hashed = hash_password(new_password)
    res = await db.users.update_many(
        {"role": {"$ne": "admin"}},
        {"$set": {
            "password_hash": hashed,
            "must_change_password": True,
            "password_updated_at": now_utc(),
        }},
    )
    return {"ok": True, "affected": res.modified_count}


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
@api.get("/settings")
async def settings_get() -> Dict[str, Any]:
    doc = await db.settings.find_one({"_id": "company"}) or {"_id": "company"}
    # normaliza: reemplaza _id por id string en respuesta
    doc["id"] = str(doc.pop("_id"))
    return doc


@api.get("/docs/manual-usuario", include_in_schema=False)
async def manual_usuario():
    """Descarga el manual de usuario legado (retro-compatibilidad)."""
    return FileResponse(
        "/app/manual/manual-usuario-megasoft.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="manual-usuario-megasoft.docx",
    )


@api.get("/docs/manual-empleado", include_in_schema=False)
async def manual_empleado():
    """Descarga el manual del empleado (inicio, cambio de contraseña, registro de rostro)."""
    return FileResponse(
        "/app/manual/manual-empleado-megasoft.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="manual-empleado-megasoft.docx",
    )


@api.get("/docs/manual-supervisor", include_in_schema=False)
async def manual_supervisor():
    """Descarga el manual del supervisor (Mi equipo, Novedades, Matriz, Horarios, Reportes)."""
    return FileResponse(
        "/app/manual/manual-supervisor-megasoft.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="manual-supervisor-megasoft.docx",
    )


@api.put("/settings")
async def settings_put(payload: SettingsIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = now_utc()
    await db.settings.update_one({"_id": "company"}, {"$set": updates}, upsert=True)
    doc = await db.settings.find_one({"_id": "company"})
    doc["id"] = str(doc.pop("_id"))
    return doc


# ==================================================================
# SITES (5 endpoints)
# ==================================================================
@api.get("/sites")
async def sites_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.sites.find({}).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/sites")
async def sites_create(payload: SiteIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["site_id"] = new_id("site")
    doc["created_at"] = now_utc()
    await db.sites.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/sites/{site_id}")
async def sites_update(site_id: str, payload: SiteIn,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Sin cambios")
    res = await db.sites.update_one({"site_id": site_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    doc = await db.sites.find_one({"site_id": site_id})
    return strip_mongo_id(doc)


@api.delete("/sites/{site_id}")
async def sites_delete(site_id: str,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.sites.delete_one({"site_id": site_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return {"ok": True}


@api.post("/sites/resolve-link")
async def sites_resolve_link(payload: SiteResolveIn,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Intenta extraer lat/lng de un link de Google Maps."""
    import re
    link = payload.link
    # patrones tipo @lat,lng o !3dlat!4dlng o q=lat,lng
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", link)
    if not m:
        m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", link)
    if not m:
        m = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", link)
    if not m:
        m = re.search(r"(-?\d+\.\d+),\s*(-?\d+\.\d+)", link)
    if not m:
        raise HTTPException(status_code=400, detail="No se pudo extraer lat/lng del link")
    return {"latitude": float(m.group(1)), "longitude": float(m.group(2))}


# ==================================================================
# DEPARTMENTS (3 endpoints)
# ==================================================================
@api.get("/departments")
async def departments_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.departments.find({}).sort("name", 1).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/departments")
async def departments_create(payload: DepartmentIn,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["department_id"] = new_id("dept", 10)
    doc["created_at"] = now_utc()
    await db.departments.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/departments/{department_id}")
async def departments_update(department_id: str, payload: DepartmentIn,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    res = await db.departments.update_one({"department_id": department_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    doc = await db.departments.find_one({"department_id": department_id})
    return strip_mongo_id(doc)


@api.delete("/departments/{department_id}")
async def departments_delete(department_id: str,
                             _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.departments.delete_one({"department_id": department_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Departamento no encontrado")
    return {"ok": True}


# ==================================================================
# SCHEDULES (3 endpoints)
# ==================================================================
async def _require_admin_or_schedules_manager(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Admin siempre puede; empleado/supervisor puede si tiene can_manage_schedules=True."""
    if user.get("role") == "admin" or user.get("can_manage_schedules"):
        return user
    raise HTTPException(status_code=403, detail="Se requiere permiso 'Puede crear y asignar horarios'.")


@api.get("/schedules")
async def schedules_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.schedules.find({}).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/schedules")
async def schedules_create(payload: ScheduleIn,
                           _: Dict[str, Any] = Depends(_require_admin_or_schedules_manager)) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["schedule_id"] = new_id("sch", 10)
    doc["created_at"] = now_utc()
    await db.schedules.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/schedules/{schedule_id}")
async def schedules_update(schedule_id: str, payload: ScheduleIn,
                           _: Dict[str, Any] = Depends(_require_admin_or_schedules_manager)) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    res = await db.schedules.update_one({"schedule_id": schedule_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    doc = await db.schedules.find_one({"schedule_id": schedule_id})
    return strip_mongo_id(doc)


@api.delete("/schedules/{schedule_id}")
async def schedules_delete(schedule_id: str,
                           _: Dict[str, Any] = Depends(_require_admin_or_schedules_manager)) -> Dict[str, bool]:
    res = await db.schedules.delete_one({"schedule_id": schedule_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    return {"ok": True}


@api.patch("/users/{user_id}/schedule")
async def users_assign_schedule(user_id: str, payload: Dict[str, Any],
                                current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Asigna (o desasigna con null) un horario a un empleado.
       Permitido a: admin, o cualquier usuario con can_manage_schedules=True
       que sea el supervisor directo del empleado objetivo."""
    schedule_id = (payload or {}).get("schedule_id")
    target = await db.users.find_one({"user_id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    is_admin = current.get("role") == "admin"
    has_perm = bool(current.get("can_manage_schedules"))
    is_supervisor_of_target = target.get("supervisor_id") == current["user_id"]

    if not (is_admin or (has_perm and is_supervisor_of_target)):
        raise HTTPException(
            status_code=403,
            detail="No autorizado. Necesitas ser admin, o supervisor del empleado con permiso 'Puede crear y asignar horarios'.",
        )

    if schedule_id:
        sch = await db.schedules.find_one({"schedule_id": schedule_id})
        if not sch:
            raise HTTPException(status_code=404, detail="Horario no encontrado")

    await db.users.update_one({"user_id": user_id}, {"$set": {"schedule_id": schedule_id or None}})
    u = await db.users.find_one({"user_id": user_id}, {"password_hash": 0, "pin_code_hash": 0})
    return strip_mongo_id(u)



# ==================================================================
# SCHEDULE ASSIGNMENTS — planificación diaria para personal sin horario fijo.
# Usada para turnos rotativos (Monitoreo, guardias, etc.) y novedades masivas.
# Colección: schedule_assignments · unique index (user_id, date).
# ==================================================================
# Tipos de novedad admitidos por el módulo de Asignación de Horarios.
# Coinciden con los códigos internos usados por las novedades regulares para que
# el motor del Reporte Matricial las contabilice sin cambios adicionales.
#   remote     → Trabajo Remoto
#   vacation   → Vacaciones
#   leave      → Reposo
#   permission → Permiso (día completo cuando se asigna aquí)
_VALID_ASSIGN_NOVELTIES = {"remote", "vacation", "leave", "permission"}


async def _ensure_assignments_index() -> None:
    try:
        await db.schedule_assignments.create_index(
            [("user_id", 1), ("date", 1)], unique=True, name="uq_user_date"
        )
    except Exception:
        pass


async def _require_admin_or_assigner(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Admin siempre; empleado/supervisor con can_assign_schedules=True también."""
    if user.get("role") == "admin" or user.get("can_assign_schedules"):
        return user
    raise HTTPException(
        status_code=403,
        detail="Se requiere permiso 'Puede asignar turnos y novedades a personal sin horario fijo'.",
    )


@api.get("/schedule-assignments/eligible-users")
async def eligible_users_for_assignments(_: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> List[Dict[str, Any]]:
    """Lista de empleados sin horario fijo — candidatos a asignación de turnos rotativos."""
    q: Dict[str, Any] = {
        "role": {"$ne": "admin"},
        "$or": [{"schedule_id": None}, {"schedule_id": ""}, {"schedule_id": {"$exists": False}}],
    }
    docs = await db.users.find(q, {"password_hash": 0, "pin_code_hash": 0}).to_list(1000)
    docs.sort(key=lambda u: (u.get("name") or "").lower())
    return [strip_mongo_id(d) for d in docs]


@api.get("/schedule-assignments")
async def list_schedule_assignments(
    from_date: str,
    to_date: str,
    user_ids: Optional[str] = None,
    _: Dict[str, Any] = Depends(_require_admin_or_assigner),
) -> List[Dict[str, Any]]:
    """Lista asignaciones en la ventana [from_date, to_date] (ISO YYYY-MM-DD).
    user_ids: lista separada por comas (opcional)."""
    q: Dict[str, Any] = {"date": {"$gte": from_date, "$lte": to_date}}
    if user_ids:
        ids = [i.strip() for i in user_ids.split(",") if i.strip()]
        if ids:
            q["user_id"] = {"$in": ids}
    docs = await db.schedule_assignments.find(q).to_list(50000)
    return [strip_mongo_id(d) for d in docs]


class AssignmentBulkIn(BaseModel):
    user_ids: List[str]
    dates: List[str]                        # ["YYYY-MM-DD", ...]
    kind: str                               # "shift" | "novelty"
    schedule_id: Optional[str] = None       # required if kind='shift'
    novelty_type: Optional[str] = None      # required if kind='novelty'


@api.post("/schedule-assignments/bulk")
async def bulk_assign(payload: AssignmentBulkIn,
                      current: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    """Upsert masivo: asigna un turno o una novedad al conjunto de (user_id × date)."""
    if not payload.user_ids or not payload.dates:
        raise HTTPException(status_code=400, detail="Debes indicar user_ids y dates")
    if payload.kind == "shift":
        if not payload.schedule_id:
            raise HTTPException(status_code=400, detail="schedule_id es obligatorio para kind='shift'")
        sch = await db.schedules.find_one({"schedule_id": payload.schedule_id})
        if not sch:
            raise HTTPException(status_code=404, detail="Horario no encontrado")
    elif payload.kind == "novelty":
        if payload.novelty_type not in _VALID_ASSIGN_NOVELTIES:
            raise HTTPException(
                status_code=400,
                detail=f"novelty_type debe ser uno de {sorted(_VALID_ASSIGN_NOVELTIES)}",
            )
    else:
        raise HTTPException(status_code=400, detail="kind debe ser 'shift' o 'novelty'")

    await _ensure_assignments_index()

    now = now_utc()
    ops = []
    from pymongo import UpdateOne
    for uid in payload.user_ids:
        for d in payload.dates:
            doc: Dict[str, Any] = {
                "user_id": uid,
                "date": d,
                "kind": payload.kind,
                "schedule_id": payload.schedule_id if payload.kind == "shift" else None,
                "novelty_type": payload.novelty_type if payload.kind == "novelty" else None,
                "updated_at": now,
                "updated_by": current["user_id"],
            }
            ops.append(UpdateOne(
                {"user_id": uid, "date": d},
                {"$set": doc,
                 "$setOnInsert": {
                     "assignment_id": new_id("asg", 10),
                     "created_at": now,
                     "created_by": current["user_id"],
                 }},
                upsert=True,
            ))
    if not ops:
        return {"ok": True, "affected": 0}
    result = await db.schedule_assignments.bulk_write(ops, ordered=False)
    return {
        "ok": True,
        "upserted": len(result.upserted_ids or {}),
        "modified": result.modified_count,
        "affected": len(ops),
    }


class AssignmentClearIn(BaseModel):
    user_ids: List[str]
    dates: List[str]


class AssignmentPlanIn(BaseModel):
    name: str
    from_date: str
    to_date: str
    user_ids: List[str] = []
    overwrite: bool = False  # Si True, elimina planes previos con rango solapado.


def _plan_public(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plan_id": doc.get("plan_id"),
        "name": doc.get("name"),
        "from_date": doc.get("from_date"),
        "to_date": doc.get("to_date"),
        "user_ids": doc.get("user_ids") or [],
    }


async def _find_overlapping_plans(from_date: str, to_date: str,
                                  exclude_plan_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Planes cuyo rango intersecta con [from_date, to_date] (inclusive)."""
    q: Dict[str, Any] = {
        "from_date": {"$lte": to_date},
        "to_date": {"$gte": from_date},
    }
    if exclude_plan_id:
        q["plan_id"] = {"$ne": exclude_plan_id}
    docs = await db.assignment_plans.find(q).sort("from_date", 1).to_list(50)
    return [_plan_public(d) for d in docs]


@api.get("/schedule-assignment-plans")
async def list_assignment_plans(_: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> List[Dict[str, Any]]:
    docs = await db.assignment_plans.find({}).sort("updated_at", -1).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/schedule-assignment-plans")
async def create_assignment_plan(payload: AssignmentPlanIn,
                                 current: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre de la planificación es obligatorio")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="El nombre no puede exceder 80 caracteres")
    if payload.from_date > payload.to_date:
        raise HTTPException(status_code=400, detail="Rango de fechas inválido")
    if await db.assignment_plans.find_one({"name": name}):
        raise HTTPException(status_code=409, detail="Ya existe una planificación con ese nombre")

    # Validación: detectar planes previos cuyo rango se cruce con el nuevo.
    overlapping = await _find_overlapping_plans(payload.from_date, payload.to_date)
    if overlapping and not payload.overwrite:
        raise HTTPException(status_code=409, detail={
            "code": "plan_range_overlap",
            "message": "Ya existen planificaciones cuyo rango de fechas se solapa con el nuevo.",
            "conflicts": overlapping,
        })
    if overlapping and payload.overwrite:
        # El usuario confirmó "reescribir" → eliminamos los planes previos solapados.
        # Las asignaciones diarias (schedule_assignments) NO se tocan; se conservan.
        await db.assignment_plans.delete_many({
            "plan_id": {"$in": [p["plan_id"] for p in overlapping]}
        })

    now = now_utc()
    doc = {
        "plan_id": new_id("plan", 10),
        "name": name,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "user_ids": payload.user_ids,
        "created_by": current["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.assignment_plans.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/schedule-assignment-plans/{plan_id}")
async def update_assignment_plan(plan_id: str, payload: AssignmentPlanIn,
                                 current: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="El nombre no puede exceder 80 caracteres")
    if payload.from_date > payload.to_date:
        raise HTTPException(status_code=400, detail="Rango de fechas inválido")
    dup = await db.assignment_plans.find_one({"name": name, "plan_id": {"$ne": plan_id}})
    if dup:
        raise HTTPException(status_code=409, detail="Ya existe otra planificación con ese nombre")

    # Validación de solape con OTROS planes (excluyendo el actual).
    overlapping = await _find_overlapping_plans(payload.from_date, payload.to_date, exclude_plan_id=plan_id)
    if overlapping and not payload.overwrite:
        raise HTTPException(status_code=409, detail={
            "code": "plan_range_overlap",
            "message": "El nuevo rango se solapa con otras planificaciones existentes.",
            "conflicts": overlapping,
        })
    if overlapping and payload.overwrite:
        await db.assignment_plans.delete_many({
            "plan_id": {"$in": [p["plan_id"] for p in overlapping]}
        })

    res = await db.assignment_plans.update_one(
        {"plan_id": plan_id},
        {"$set": {
            "name": name,
            "from_date": payload.from_date,
            "to_date": payload.to_date,
            "user_ids": payload.user_ids,
            "updated_at": now_utc(),
            "updated_by": current["user_id"],
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Planificación no encontrada")
    doc = await db.assignment_plans.find_one({"plan_id": plan_id})
    return strip_mongo_id(doc)


@api.delete("/schedule-assignment-plans/{plan_id}")
async def delete_assignment_plan(plan_id: str,
                                 _: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, bool]:
    res = await db.assignment_plans.delete_one({"plan_id": plan_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Planificación no encontrada")
    return {"ok": True}


@api.post("/schedule-assignments/clear")
async def bulk_clear(payload: AssignmentClearIn,
                     _: Dict[str, Any] = Depends(_require_admin_or_assigner)) -> Dict[str, Any]:
    """Elimina asignaciones para el conjunto de (user_id × date)."""
    if not payload.user_ids or not payload.dates:
        raise HTTPException(status_code=400, detail="Debes indicar user_ids y dates")
    result = await db.schedule_assignments.delete_many({
        "user_id": {"$in": payload.user_ids},
        "date": {"$in": payload.dates},
    })
    return {"ok": True, "deleted": result.deleted_count}


# ==================================================================
# KIOSK (5 endpoints)
# ==================================================================
@api.post("/kiosk/unlock")
async def kiosk_unlock(payload: KioskUnlockIn) -> Dict[str, Any]:
    """Admin desbloquea el modo kiosco con sus credenciales."""
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if (not user or user.get("role") != "admin"
            or not verify_password(payload.password, user.get("password_hash", ""))):
        raise HTTPException(status_code=401, detail="Credenciales de administrador inválidas")
    settings = await db.settings.find_one({"_id": "company"}) or {}
    if not settings.get("kiosk_enabled", True):
        raise HTTPException(status_code=403, detail="Modo kiosco deshabilitado")
    return {"ok": True, "unlocked_by": user["user_id"], "unlocked_at": now_utc().isoformat()}


@api.post("/kiosk/unlock-face")
async def kiosk_unlock_face(payload: KioskFaceUnlockIn) -> Dict[str, Any]:
    """Admin desbloquea el modo kiosco con su rostro (face-api descriptor)."""
    desc = payload.face_descriptor or []
    if len(desc) != 128:
        raise HTTPException(status_code=400, detail="Descriptor facial inválido (se esperan 128 dimensiones)")

    settings = await db.settings.find_one({"_id": "company"}) or {}
    if not settings.get("kiosk_enabled", True):
        raise HTTPException(status_code=403, detail="Modo kiosco deshabilitado")

    admins = await db.users.find(
        {"role": "admin", "face_descriptor": {"$exists": True, "$ne": None, "$not": {"$size": 0}}},
        {"user_id": 1, "name": 1, "face_descriptor": 1, "_id": 0},
    ).to_list(200)
    if not admins:
        raise HTTPException(status_code=404, detail="No hay administradores con rostro registrado")

    import math as _math
    best = None
    second = None
    for a in admins:
        ref = a.get("face_descriptor") or []
        if len(ref) != 128:
            continue
        dist = _math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(ref, desc)))
        if best is None or dist < best[1]:
            second = best
            best = (a, dist)
        elif second is None or dist < second[1]:
            second = (a, dist)

    if not best:
        raise HTTPException(status_code=401, detail="No se pudo comparar el rostro")

    THRESHOLD = 0.48
    MARGIN = 0.06
    admin, dist = best
    if dist > THRESHOLD:
        raise HTTPException(status_code=401, detail=f"Rostro no reconocido (distancia {dist:.3f} > {THRESHOLD})")
    if second is not None and (second[1] - dist) < MARGIN:
        raise HTTPException(
            status_code=401,
            detail="Rostro ambiguo entre dos administradores. Intenta de nuevo con mejor iluminación.",
        )
    return {
        "ok": True,
        "unlocked_by": admin["user_id"],
        "admin_name": admin["name"],
        "distance": round(dist, 4),
        "unlocked_at": now_utc().isoformat(),
    }


@api.get("/kiosk/sites")
async def kiosk_sites() -> List[Dict[str, Any]]:
    """Lista pública de sedes para el selector del Kiosco (no requiere sesión).
    El Kiosco se autentica primero con contraseña de admin (/kiosk/unlock)
    antes de asociarse a una sede via /kiosk/session/open."""
    docs = await db.sites.find({}, {"site_id": 1, "name": 1, "address": 1, "_id": 0}).to_list(500)
    docs.sort(key=lambda s: (s.get("name") or "").lower())
    return docs


@api.get("/kiosk/roster")
async def kiosk_roster() -> List[Dict[str, Any]]:
    """Lista de usuarios con datos mínimos para reconocimiento en el kiosco."""
    docs = await db.users.find(
        {"onboarded": True},
        {"user_id": 1, "name": 1, "cedula": 1, "role": 1, "picture": 1, "site_id": 1,
         "department_id": 1, "schedule_id": 1, "position": 1,
         "selfie_base64": 1, "face_descriptor": 1, "_id": 0},
    ).to_list(2000)
    return docs


# ---- Kiosk Sessions (1 activo por sede) ---------------------------
# TTL: se considera "activo" si el heartbeat es reciente (< 5 min).
KIOSK_SESSION_TTL_MIN = 5


@api.post("/kiosk/session/open", include_in_schema=False)
async def kiosk_session_open(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    site_id = (payload or {}).get("site_id")
    if not site_id:
        raise HTTPException(status_code=400, detail="Falta site_id")
    site = await db.sites.find_one({"site_id": site_id})
    if not site:
        raise HTTPException(status_code=404, detail="Sede no registrada")

    # Si el request viene autenticado como un usuario `kiosk` cuya `site_id`
    # coincide con la sede solicitada, se cierra automáticamente la sesión
    # previa (típico caso: la tablet perdió energía y quedó una sesión huérfana).
    force_from_kiosk_user = False
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            payload_jwt = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            uid = payload_jwt.get("sub")
            if uid:
                requester = await db.users.find_one({"user_id": uid})
                if (requester and requester.get("role") == "kiosk"
                        and requester.get("site_id") == site_id):
                    force_from_kiosk_user = True
        except jwt.PyJWTError:
            pass

    cutoff = now_utc() - timedelta(minutes=KIOSK_SESSION_TTL_MIN)
    existing = await db.kiosk_sessions.find_one({
        "site_id": site_id,
        "closed_at": None,
        "last_heartbeat": {"$gte": cutoff},
    })
    if existing:
        if force_from_kiosk_user:
            # Cierra la sesión anterior — la nueva viene de un usuario Kiosco
            # legítimo para esta sede.
            await db.kiosk_sessions.update_many(
                {"site_id": site_id, "closed_at": None},
                {"$set": {"closed_at": now_utc(), "closed_forced": True,
                          "closed_reason": "kiosk_user_re_open"}},
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe un kiosco activo para la sede '{site.get('name') or site_id}'. "
                       f"Ciérralo antes de abrir uno nuevo.",
            )
    session_id = new_id("kiosk_sess", 12)
    await db.kiosk_sessions.insert_one({
        "session_id": session_id,
        "site_id": site_id,
        "site_name": site.get("name"),
        "opened_at": now_utc(),
        "last_heartbeat": now_utc(),
        "closed_at": None,
    })
    return {"session_id": session_id, "site_id": site_id, "site_name": site.get("name")}


@api.post("/kiosk/session/heartbeat", include_in_schema=False)
async def kiosk_session_heartbeat(payload: Dict[str, Any]) -> Dict[str, bool]:
    session_id = (payload or {}).get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Falta session_id")
    res = await db.kiosk_sessions.update_one(
        {"session_id": session_id, "closed_at": None},
        {"$set": {"last_heartbeat": now_utc()}},
    )
    return {"ok": res.matched_count > 0}


@api.post("/kiosk/session/close", include_in_schema=False)
async def kiosk_session_close(payload: Dict[str, Any]) -> Dict[str, bool]:
    session_id = (payload or {}).get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Falta session_id")
    await db.kiosk_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"closed_at": now_utc()}},
    )
    return {"ok": True}


@api.get("/admin/kiosk/sessions")
async def admin_kiosk_sessions_list(_: Dict[str, Any] = Depends(require_roles("admin"))) -> List[Dict[str, Any]]:
    """Lista de sesiones de kiosco activas (heartbeat reciente). Uso: liberación manual desde Ajustes."""
    cutoff = now_utc() - timedelta(minutes=KIOSK_SESSION_TTL_MIN)
    docs = await db.kiosk_sessions.find({
        "closed_at": None,
        "last_heartbeat": {"$gte": cutoff},
    }).sort("opened_at", -1).to_list(200)
    # Incluye también sesiones "colgadas" (sin heartbeat reciente) para permitir cerrarlas.
    stale = await db.kiosk_sessions.find({
        "closed_at": None,
        "last_heartbeat": {"$lt": cutoff},
    }).sort("opened_at", -1).to_list(200)
    def _fmt(d, stale_flag):
        return {
            "session_id": d.get("session_id"),
            "site_id": d.get("site_id"),
            "site_name": d.get("site_name"),
            "opened_at": d.get("opened_at").isoformat() if d.get("opened_at") else None,
            "last_heartbeat": d.get("last_heartbeat").isoformat() if d.get("last_heartbeat") else None,
            "stale": stale_flag,
        }
    return [_fmt(d, False) for d in docs] + [_fmt(d, True) for d in stale]


@api.post("/admin/kiosk/sessions/force-close")
async def admin_kiosk_session_force_close(payload: Dict[str, Any],
                                          _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Cierra manualmente una o varias sesiones de kiosco.
    Payload admite: {session_id}  ó  {site_id}  (libera todas las activas de esa sede)."""
    session_id = (payload or {}).get("session_id")
    site_id = (payload or {}).get("site_id")
    if not session_id and not site_id:
        raise HTTPException(status_code=400, detail="Envía 'session_id' o 'site_id'")
    q: Dict[str, Any] = {"closed_at": None}
    if session_id:
        q["session_id"] = session_id
    if site_id:
        q["site_id"] = site_id
    res = await db.kiosk_sessions.update_many(q, {"$set": {"closed_at": now_utc(), "closed_forced": True}})
    return {"ok": True, "closed": res.modified_count}


@api.post("/kiosk/verify-pin")
async def kiosk_verify_pin(payload: KioskPinIn) -> Dict[str, bool]:
    user = await db.users.find_one({"user_id": payload.user_id})
    if not user or not user.get("pin_code_hash"):
        raise HTTPException(status_code=404, detail="Usuario o PIN no configurado")
    if not verify_password(payload.pin, user["pin_code_hash"]):
        raise HTTPException(status_code=401, detail="PIN incorrecto")
    return {"ok": True}


@api.post("/kiosk/attendance/check")
async def kiosk_attendance_check(payload: KioskAttendanceIn) -> Dict[str, Any]:
    user = await db.users.find_one({"user_id": payload.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Auto-detect: si no se especifica type o es "auto", el sistema decide
    # basándose en la última marca del día del empleado.
    effective_type = payload.type
    if effective_type in (None, "auto"):
        effective_type = await _resolve_next_type(payload.user_id)

    return await _register_attendance(user, effective_type, payload.latitude, payload.longitude,
                                      payload.site_id, payload.selfie_base64, method="kiosk")


async def _resolve_next_type(user_id: str) -> str:
    """Determina la próxima marca (in/out) según la última del día en curso.
    Sin marcas hoy o última fue "out" → "in". Última fue "in" → "out"."""
    local_now = now_utc().astimezone(APP_TZ)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    last = await db.attendance.find_one(
        {"user_id": user_id, "timestamp": {"$gte": day_start}},
        sort=[("timestamp", -1)],
        projection={"type": 1, "_id": 0},
    )
    if not last or last.get("type") == "out":
        return "in"
    return "out"


@api.get("/kiosk/next-type/{user_id}")
async def kiosk_next_type(user_id: str) -> Dict[str, str]:
    """Retorna el próximo tipo de marca que corresponde al usuario en el día."""
    user = await db.users.find_one({"user_id": user_id}, {"user_id": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"next_type": await _resolve_next_type(user_id)}


@api.post("/kiosk/reenroll-face")
async def kiosk_reenroll_face(user_id: str = Form(...), pin: str = Form(...),
                              selfie_base64: str = Form(...),
                              face_descriptor: Optional[str] = Form(None)) -> Dict[str, bool]:
    user = await db.users.find_one({"user_id": user_id})
    if not user or not user.get("pin_code_hash") or not verify_password(pin, user["pin_code_hash"]):
        raise HTTPException(status_code=401, detail="PIN incorrecto")
    updates: Dict[str, Any] = {"selfie_base64": selfie_base64, "onboarded": True}
    if face_descriptor:
        import json as _json
        try:
            updates["face_descriptor"] = _json.loads(face_descriptor)
        except Exception:
            pass
    await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
    return {"ok": True}


# ==================================================================
# ATTENDANCE (5 endpoints)
# ==================================================================
async def _register_attendance(user: Dict[str, Any], type_: str,
                               latitude: Optional[float], longitude: Optional[float],
                               site_id: Optional[str], selfie_base64: Optional[str],
                               method: str = "web") -> Dict[str, Any]:
    site = None
    if site_id:
        site = await db.sites.find_one({"site_id": site_id})
    elif user.get("site_id"):
        site = await db.sites.find_one({"site_id": user["site_id"]})

    # Geocerca deshabilitada — la ubicación se registra sólo con fines de auditoría.
    within = None

    # Cálculo de tardanza (solo para "in") — clasificación dual
    #   • on_time     → dentro de tolerancia general
    #   • late_minor  → excede tolerancia general, dentro de la ventana de justificación
    #   • late_major  → excede ambas tolerancias (obligatorio justificar)
    is_late, late_min = False, 0
    late_severity = "on_time"
    requires_justification = False
    if type_ == "in" and user.get("schedule_id"):
        sched = await db.schedules.find_one({"schedule_id": user["schedule_id"]})
        if sched and sched.get("blocks"):
            local_now = now_utc().astimezone(APP_TZ)
            first_block = sched["blocks"][0]
            hh, mm = map(int, first_block["start"].split(":"))
            expected = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            tol_general = int(sched.get("tolerance_minutes", 10))
            tol_justif = int(sched.get("justification_tolerance_minutes", 20))
            delta = int((local_now - expected).total_seconds() // 60)
            if delta > tol_general:
                is_late = True
                late_min = delta
                if delta > (tol_general + tol_justif):
                    late_severity = "late_major"
                    requires_justification = True
                else:
                    late_severity = "late_minor"

    doc = {
        "record_id": new_id("att", 12),
        "user_id": user["user_id"],
        "type": type_,
        "timestamp": now_utc(),
        "latitude": latitude,
        "longitude": longitude,
        "site_id": site["site_id"] if site else site_id,
        "within_geofence": within,
        "is_late": is_late,
        "late_minutes": late_min,
        "late_severity": late_severity,
        "requires_justification": requires_justification,
        "justification": None,
        "method": method,
    }
    if selfie_base64:
        doc["selfie_base64"] = selfie_base64
    await db.attendance.insert_one(doc)
    return strip_mongo_id(doc)


@api.post("/attendance/check")
async def attendance_check(payload: AttendanceCheckIn,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return await _register_attendance(user, payload.type, payload.latitude, payload.longitude,
                                      payload.site_id, payload.selfie_base64, method="web")


@api.get("/attendance/me")
async def attendance_me(limit: int = 100,
                        user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.attendance.find(
        {"user_id": user["user_id"]},
        {"selfie_base64": 0},
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return [strip_mongo_id(d) for d in docs]


@api.get("/attendance/today")
async def attendance_today(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    local_now = now_utc().astimezone(APP_TZ)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    docs = await db.attendance.find(
        {"user_id": user["user_id"], "timestamp": {"$gte": start, "$lt": end}},
        {"selfie_base64": 0},
    ).sort("timestamp", 1).to_list(50)
    return [strip_mongo_id(d) for d in docs]


@api.get("/attendance/team")
async def attendance_team(days: int = 7,
                          user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"timestamp": {"$gte": now_utc() - timedelta(days=days)}}
    if user["role"] in LEADER_ROLES:
        team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
        team_ids = [t["user_id"] for t in team]
        query["user_id"] = {"$in": team_ids}
    docs = await db.attendance.find(query, {"selfie_base64": 0}).sort("timestamp", -1).limit(1000).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/attendance/justify")
async def attendance_justify(payload: JustifyIn,
                             user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    query = {"record_id": payload.record_id}
    if user["role"] == "employee":
        query["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        query["user_id"] = {"$in": await supervisor_scope_ids(user)}
    res = await db.attendance.update_one(
        query,
        {"$set": {"justification": payload.justification, "requires_justification": False}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return {"ok": True}


# ==================================================================
# NOVELTIES (4 endpoints)
# ==================================================================
@api.get("/novelties")
async def novelties_list(user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if user["role"] == "employee":
        q["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
        team_ids = [t["user_id"] for t in team] + [user["user_id"]]
        q["user_id"] = {"$in": team_ids}
    docs = await db.novelties.find(q).sort("created_at", -1).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/novelties")
async def novelties_create(payload: NoveltyIn,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    target = payload.user_id or user["user_id"]
    if target != user["user_id"] and user["role"] not in LEADER_OR_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")
    if user["role"] in LEADER_ROLES and target != user["user_id"]:
        team_ids = await supervisor_scope_ids(user)
        if target not in team_ids:
            raise HTTPException(status_code=403, detail="El empleado no pertenece a tu equipo")
    # Validación: rango horario obligatorio salvo para vacaciones
    if payload.type != "vacation":
        if not payload.start_time or not payload.end_time:
            raise HTTPException(status_code=400,
                                detail="Debes indicar rango horario (hora inicio y hora fin)")
        if payload.start_time >= payload.end_time and payload.start_date == payload.end_date:
            raise HTTPException(status_code=400,
                                detail="La hora fin debe ser mayor a la hora inicio")
    doc = {
        "novelty_id": new_id("nv", 12),
        "user_id": target,
        "type": payload.type,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "start_time": payload.start_time if payload.type != "vacation" else None,
        "end_time": payload.end_time if payload.type != "vacation" else None,
        "reason": payload.reason,
        "status": "pending",
        "created_by": user["user_id"],
        "created_at": now_utc(),
        "decided_at": None,
        "decided_by": None,
        "decision_comment": None,
    }
    await db.novelties.insert_one(doc)
    return strip_mongo_id(doc)


@api.delete("/novelties/{novelty_id}")
async def novelties_delete(novelty_id: str,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    q: Dict[str, Any] = {"novelty_id": novelty_id}
    # Admin puede borrar cualquier novedad en cualquier estado.
    if user["role"] in LEADER_ROLES:
        # Supervisor puede borrar novedades de su equipo (cualquier estado).
        q["user_id"] = {"$in": await supervisor_scope_ids(user)}
    elif user["role"] != "admin":
        # Empleados solo las suyas y solo si están pendientes.
        q["user_id"] = user["user_id"]
        q["status"] = "pending"
    res = await db.novelties.delete_one(q)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    return {"ok": True}


@api.patch("/novelties/{novelty_id}")
async def novelties_patch(novelty_id: str,
                          payload: NoveltyPatchIn,
                          user: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Solo administradores pueden modificar cualquier campo de una novedad."""
    doc = await db.novelties.find_one({"novelty_id": novelty_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    updates: Dict[str, Any] = {}
    data = payload.model_dump(exclude_none=True)
    # Si cambia el tipo a "vacation", quita horas
    if data.get("type") == "vacation":
        data["start_time"] = None
        data["end_time"] = None
    for field in ("type", "start_date", "end_date", "start_time", "end_time",
                  "reason", "status", "decision_comment", "user_id"):
        if field in data:
            updates[field] = data[field]
    if updates.get("status") in ("approved", "rejected"):
        updates["decided_at"] = now_utc()
        updates["decided_by"] = user["user_id"]
    if not updates:
        return {"ok": True, "unchanged": True}
    await db.novelties.update_one({"novelty_id": novelty_id}, {"$set": updates})
    return {"ok": True, "updated_fields": list(updates.keys())}


@api.post("/novelties/bulk-decide")
async def novelties_bulk_decide(payload: NoveltyDecideIn,
                                user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, int]:
    q: Dict[str, Any] = {"novelty_id": {"$in": payload.novelty_ids}, "status": "pending"}
    if user["role"] in LEADER_ROLES:
        q["user_id"] = {"$in": await supervisor_scope_ids(user)}
    res = await db.novelties.update_many(
        q,
        {"$set": {"status": payload.decision, "decided_at": now_utc(),
                  "decided_by": user["user_id"], "decision_comment": payload.comment}},
    )
    return {"updated": res.modified_count}



# ==================================================================
# VISITS (Control de Visitas) — 6 endpoints
# ==================================================================
@api.post("/users/{user_id}/visit-permissions")
async def set_visit_permissions(
    user_id: str,
    payload: UserPermissionsIn,
    _: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, Any]:
    """Admin toggles can_create_visits / can_view_visit_logs on a user."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return {"ok": True, "changed": 0}
    res = await db.users.update_one({"user_id": user_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True, "changed": res.modified_count, "updates": updates}


@api.post("/visits")
async def create_visit(payload: VisitIn,
                       user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not user.get("can_create_visits") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para crear visitas")
    if payload.type not in ("personal", "laboral"):
        raise HTTPException(status_code=400, detail="type debe ser 'personal' o 'laboral'")
    if not payload.visitors:
        raise HTTPException(status_code=400, detail="Debe registrar al menos un visitante")

    host = await db.users.find_one({"user_id": payload.host_user_id}, {"user_id": 1, "name": 1, "_id": 0})
    if not host:
        raise HTTPException(status_code=404, detail="Empleado anfitrión no encontrado")

    if payload.type == "laboral":
        if not payload.company_name:
            raise HTTPException(status_code=400, detail="Nombre de empresa requerido para visita laboral")
        # Validación del motivo (catálogo fijo con opción “Otra”)
        if not payload.purpose or payload.purpose not in VISIT_PURPOSE_CATALOG:
            raise HTTPException(status_code=400,
                                detail="Selecciona un motivo válido del catálogo")
        if payload.purpose == "otra" and not (payload.purpose_other or "").strip():
            raise HTTPException(status_code=400,
                                detail="Debes especificar el motivo cuando eliges “Otra”")
        for v in payload.visitors:
            if not v.phone:
                raise HTTPException(status_code=400, detail="Cada visitante laboral requiere teléfono")
            if not v.cedula:
                raise HTTPException(status_code=400, detail="Cada visitante laboral requiere cédula")
    else:  # personal
        for v in payload.visitors:
            # En visitas personales: cédula obligatoria salvo que sea menor de edad
            if not v.cedula and not v.is_minor:
                raise HTTPException(status_code=400,
                                    detail="Cédula requerida (o marcar como menor de edad)")

    obs = (payload.observations or "").strip()
    if len(obs) > 300:
        raise HTTPException(status_code=400, detail="Observaciones no puede exceder 300 caracteres")

    visit_id = new_id("visit", 10)
    # NOTA: Ya no se genera un PIN aleatorio. La autenticación en el kiosco
    # se realiza por visitante usando los últimos 3 dígitos de la cédula del
    # visitante (endpoint /kiosk/visits/{id}/verify-visitor). Menos fricción
    # y sin confusión con un "PIN" adicional que había que compartir.
    doc = {
        "visit_id": visit_id,
        "type": payload.type,
        "host_user_id": payload.host_user_id,
        "host_name": host.get("name"),
        "scheduled_at": payload.scheduled_at or now_utc(),
        "company_name": payload.company_name if payload.type == "laboral" else None,
        # Motivo — nuevo catálogo
        "purpose": payload.purpose if payload.type == "laboral" else None,
        "purpose_label": (VISIT_PURPOSE_CATALOG.get(payload.purpose) if payload.type == "laboral" else None),
        "purpose_other": (payload.purpose_other.strip() if payload.type == "laboral" and payload.purpose == "otra" and payload.purpose_other else None),
        # Observaciones (nuevo campo, 300 caracteres)
        "observations": obs or None,
        # Retrocompat — se conservan los campos originales si el cliente antiguo los envía.
        "motive": payload.motive,
        "notes": payload.notes,
        "visitors": [v.model_dump() for v in payload.visitors],
        "selfies": [],
        "status": "pending",
        "created_at": now_utc(),
        "created_by": user["user_id"],
    }
    await db.visits.insert_one(doc)
    return {"visit_id": visit_id, "ok": True}


@api.get("/visits")
async def list_visits(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    type: Optional[str] = None,
    host_user_id: Optional[str] = None,
    company_name: Optional[str] = None,
    status: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver visitas")

    q: Dict[str, Any] = {}
    if from_date or to_date:
        rng: Dict[str, Any] = {}
        if from_date:
            rng["$gte"] = datetime.fromisoformat(from_date).replace(tzinfo=APP_TZ).astimezone(timezone.utc)
        if to_date:
            rng["$lt"] = (datetime.fromisoformat(to_date).replace(tzinfo=APP_TZ) + timedelta(days=1)).astimezone(timezone.utc)
        q["scheduled_at"] = rng
    if type:
        q["type"] = type
    if host_user_id:
        q["host_user_id"] = host_user_id
    if company_name:
        q["company_name"] = {"$regex": company_name, "$options": "i"}
    if status:
        q["status"] = status

    docs = []
    async for d in db.visits.find(q).sort("scheduled_at", -1).limit(500):
        d.pop("_id", None)
        d["selfies_count"] = len(d.get("selfies") or [])
        d.pop("selfies", None)
        docs.append(d)
    return docs


@api.get("/visits/{visit_id}")
async def get_visit(visit_id: str,
                    user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver visitas")
    d = await db.visits.find_one({"visit_id": visit_id})
    if not d:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    d.pop("_id", None)
    return d


@api.get("/kiosk/pending-visits/{host_user_id}")
async def kiosk_pending_visits(host_user_id: str) -> List[Dict[str, Any]]:
    today_local = now_utc().astimezone(APP_TZ)
    start = today_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = (today_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)
    docs = []
    async for v in db.visits.find(
        {"host_user_id": host_user_id,
         "status": {"$in": ["pending", "in_progress"]},
         "scheduled_at": {"$gte": start, "$lt": end}}
    ).sort("scheduled_at", 1):
        v.pop("_id", None)
        v.pop("selfies", None)
        v.pop("check_in_pin", None)  # campo legacy — no se usa
        docs.append(v)
    return docs


@api.get("/kiosk/visits/today")
async def kiosk_visits_today() -> List[Dict[str, Any]]:
    """Listado público de todas las visitas activas del día para el Kiosco.
    Se autentican después con los 3 últimos dígitos de la cédula del visitante."""
    today_local = now_utc().astimezone(APP_TZ)
    start = today_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = (today_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc)
    docs: List[Dict[str, Any]] = []
    async for v in db.visits.find(
        {"status": {"$in": ["pending", "in_progress"]},
         "scheduled_at": {"$gte": start, "$lt": end}}
    ).sort("scheduled_at", 1):
        visitors = v.get("visitors") or []
        # Devuelve sólo lo necesario para pintar el listado; NUNCA el PIN.
        docs.append({
            "visit_id": v.get("visit_id"),
            "type": v.get("type"),
            "host_name": v.get("host_name"),
            "company_name": v.get("company_name"),
            "purpose_label": v.get("purpose_label"),
            "purpose_other": v.get("purpose_other"),
            "observations": v.get("observations"),
            "scheduled_at": v.get("scheduled_at").isoformat() if v.get("scheduled_at") else None,
            "visitors_count": len(visitors),
            # Nombres de visitantes (para la vista "Visita Seleccionada"); la cédula
            # completa queda oculta — sólo se expone al validar los 3 dígitos.
            "visitors": [{"name": vs.get("name")} for vs in visitors],
            "primary_visitor_name": (visitors[0].get("name") if visitors else None),
            "status": v.get("status"),
        })
    return docs


@api.post("/kiosk/visits/{visit_id}/verify-visitor")
async def kiosk_verify_visitor_pin(visit_id: str, payload: VisitorPinIn) -> Dict[str, Any]:
    """Valida los últimos 3 dígitos de la cédula del visitante indicado.
    Se usa en el nuevo flujo de recepción: cada visitante se autentica por
    separado con los 3 últimos dígitos de su documento antes de la selfie."""
    pin = (payload.pin or "").strip()
    if not pin or not pin.isdigit() or len(pin) != 3:
        raise HTTPException(status_code=400, detail="El PIN debe ser numérico de 3 dígitos")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if doc.get("status") not in ("pending", "in_progress"):
        raise HTTPException(status_code=400, detail="Esta visita ya fue completada o cancelada")
    visitors = doc.get("visitors") or []
    idx = payload.visitor_index
    if idx < 0 or idx >= len(visitors):
        raise HTTPException(status_code=400, detail="Índice de visitante inválido")
    visitor = visitors[idx]
    cedula = (visitor.get("cedula") or "")
    # Extrae únicamente dígitos para tolerar formatos "V-12345678", "12.345.678", etc.
    digits = "".join(ch for ch in cedula if ch.isdigit())
    if len(digits) < 3:
        raise HTTPException(status_code=400,
                            detail="La cédula del visitante no permite validación por 3 dígitos")
    if digits[-3:] != pin:
        raise HTTPException(status_code=403, detail="Los 3 dígitos no coinciden con la cédula del visitante")
    return {"ok": True, "visitor": {"name": visitor.get("name"), "cedula": cedula}}


@api.post("/visits/{visit_id}/capture-selfie")
async def capture_visit_selfie(visit_id: str, payload: VisitSelfieIn) -> Dict[str, Any]:
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if payload.visitor_index < 0 or payload.visitor_index >= len(doc.get("visitors") or []):
        raise HTTPException(status_code=400, detail="visitor_index fuera de rango")
    if not payload.selfie_base64 or not payload.selfie_base64.startswith("data:image"):
        raise HTTPException(status_code=400, detail="selfie_base64 inválido")

    selfies = doc.get("selfies") or []
    selfies = [s for s in selfies if s.get("visitor_index") != payload.visitor_index]
    selfies.append({
        "visitor_index": payload.visitor_index,
        "selfie_base64": payload.selfie_base64,
        "captured_at": now_utc(),
    })
    total_visitors = len(doc.get("visitors") or [])
    new_status = "completed" if len(selfies) >= total_visitors else "in_progress"
    updates: Dict[str, Any] = {"selfies": selfies, "status": new_status}
    if new_status == "completed":
        updates["completed_at"] = now_utc()
    await db.visits.update_one({"visit_id": visit_id}, {"$set": updates})
    return {"ok": True, "status": new_status, "captured": len(selfies), "total": total_visitors}


@api.post("/visits/{visit_id}/close")
async def close_visit(visit_id: str,
                      user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Cierra manualmente una visita: registra exit_at y cambia status='closed'.
       Requiere can_view_visit_logs o rol admin.
       Un usuario no-admin solo puede cerrar visitas que él mismo creó."""
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para cerrar visitas")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if user.get("role") != "admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403,
                            detail="Solo puedes cerrar visitas que tú hayas programado")
    if doc.get("status") == "closed":
        raise HTTPException(status_code=400, detail="La visita ya está cerrada")
    exit_at = now_utc()
    scheduled_at = doc.get("scheduled_at") or doc.get("created_at")
    duration_min = None
    if scheduled_at:
        if isinstance(scheduled_at, datetime):
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            raw = (exit_at - scheduled_at).total_seconds() / 60
            duration_min = round(max(0.0, raw), 1)  # clamp para evitar negativos si scheduled_at es futuro
    await db.visits.update_one(
        {"visit_id": visit_id},
        {"$set": {
            "status": "closed",
            "exit_at": exit_at,
            "duration_minutes": duration_min,
            "closed_by": user["user_id"],
        }},
    )
    return {"ok": True, "exit_at": exit_at.isoformat(), "duration_minutes": duration_min}


@api.delete("/visits/{visit_id}")
async def delete_visit(visit_id: str,
                       user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    """Elimina una visita. Un usuario no-admin solo puede borrar visitas que él mismo creó.
       Requiere can_view_visit_logs o rol admin."""
    if not user.get("can_view_visit_logs") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar visitas")
    doc = await db.visits.find_one({"visit_id": visit_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Visita no encontrada")
    if user.get("role") != "admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403,
                            detail="Solo puedes eliminar visitas que tú hayas programado")
    await db.visits.delete_one({"visit_id": visit_id})
    return {"ok": True}



# ==================================================================
# BACKUP / RESTORE (3 endpoints — admin only)
# ==================================================================
# Colecciones exportables. `attendance` queda excluida por regla del producto.
EXPORTABLE_COLLECTIONS = [
    "users", "sites", "departments", "schedules",
    "novelties", "visits", "settings",
]


def _serialize_doc(d: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte tipos no-JSON (datetime, ObjectId) a strings."""
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, list):
            out[k] = [_serialize_doc(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, dict):
            out[k] = _serialize_doc(v)
        else:
            out[k] = v
    return out


@api.get("/admin/collections", include_in_schema=False)
async def admin_collections(_: Dict[str, Any] = Depends(require_roles("admin"))) -> List[Dict[str, Any]]:
    """Lista colecciones exportables con conteo de documentos."""
    out = []
    for name in EXPORTABLE_COLLECTIONS:
        n = await db[name].count_documents({})
        out.append({"name": name, "count": n})
    return out


@api.post("/admin/export", include_in_schema=False)
async def admin_export(payload: Dict[str, Any],
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> StreamingResponse:
    """Exporta las colecciones seleccionadas como JSON."""
    selected = payload.get("collections") or []
    selected = [c for c in selected if c in EXPORTABLE_COLLECTIONS]
    if not selected:
        raise HTTPException(status_code=400, detail="Selecciona al menos una colección")
    dump: Dict[str, Any] = {
        "app": "megasoft-asistencia",
        "generated_at": now_utc().isoformat(),
        "collections": {},
    }
    for name in selected:
        docs = await db[name].find({}).to_list(20000)
        dump["collections"][name] = [_serialize_doc(d) for d in docs]
    payload_bytes = json.dumps(dump, ensure_ascii=False, indent=2).encode("utf-8")
    ts = now_utc().strftime("%Y%m%d_%H%M%S")
    filename = f"megasoft-backup-{ts}.json"
    return StreamingResponse(
        iter([payload_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api.post("/admin/import", include_in_schema=False)
async def admin_import(file: UploadFile = File(...),
                       mode: str = "upsert",
                       collections: Optional[str] = None,
                       _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    """Importa un backup JSON.
    - mode='upsert' (por defecto): inserta o actualiza según llave natural.
    - mode='replace': elimina todos los documentos existentes de esa colección y reemplaza.
    - collections: lista separada por comas para restaurar solo ciertas colecciones.
    """
    if mode not in {"upsert", "replace"}:
        raise HTTPException(status_code=400, detail="mode debe ser 'upsert' o 'replace'")
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON inválido: {e}")
    if not isinstance(payload, dict) or "collections" not in payload:
        raise HTTPException(status_code=400, detail="Archivo no reconocido")

    filter_list = set()
    if collections:
        filter_list = {c.strip() for c in collections.split(",") if c.strip()}

    # llave natural por colección para upsert
    NAT_KEYS = {
        "users": "user_id", "sites": "site_id", "departments": "department_id",
        "schedules": "schedule_id", "novelties": "novelty_id",
        "visits": "visit_id", "settings": "_id",
    }
    summary: Dict[str, Any] = {"restored": {}, "skipped": {}, "mode": mode}
    for name, docs in (payload.get("collections") or {}).items():
        if name == "attendance":
            summary["skipped"][name] = "asistencia excluida por regla del producto"
            continue
        if name not in EXPORTABLE_COLLECTIONS:
            summary["skipped"][name] = "colección no permitida"
            continue
        if filter_list and name not in filter_list:
            summary["skipped"][name] = "no seleccionada"
            continue
        if not isinstance(docs, list):
            summary["skipped"][name] = "formato inválido"
            continue

        # Limpia campos no reinsertables y convierte ISO string → datetime en campos de tiempo
        cleaned = []
        for d in docs:
            if not isinstance(d, dict):
                continue
            doc = dict(d)
            doc.pop("_id", None)  # deja que Mongo asigne uno nuevo si es replace
            for tk in ("created_at", "updated_at", "decided_at", "exit_at", "timestamp"):
                if tk in doc and isinstance(doc[tk], str):
                    try:
                        doc[tk] = datetime.fromisoformat(doc[tk].replace("Z", "+00:00"))
                    except Exception:
                        pass
            cleaned.append(doc)

        if mode == "replace":
            await db[name].delete_many({})
            if cleaned:
                await db[name].insert_many(cleaned)
            summary["restored"][name] = len(cleaned)
        else:  # upsert
            key = NAT_KEYS.get(name)
            n_up = 0
            for doc in cleaned:
                if name == "settings":
                    await db.settings.update_one({"_id": "company"}, {"$set": doc}, upsert=True)
                    n_up += 1
                elif key and doc.get(key) is not None:
                    await db[name].update_one({key: doc[key]}, {"$set": doc}, upsert=True)
                    n_up += 1
                else:
                    await db[name].insert_one(doc)
                    n_up += 1
            summary["restored"][name] = n_up

    return summary


# ==================================================================
# STATS / REPORTS (3 endpoints)
# ==================================================================
@api.get("/stats/executive")
async def stats_executive(days: int = 30,
                          user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, Any]:
    """Métricas ejecutivas: top tardanzas, ranking por depto, promedio minutos tarde."""
    since = now_utc() - timedelta(days=days)
    q = {"timestamp": {"$gte": since}, "type": "in"}

    scope_users_q: Dict[str, Any] = {}
    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        q["user_id"] = {"$in": team_ids}
        scope_users_q = {"user_id": {"$in": team_ids}}

    users = {u["user_id"]: u async for u in db.users.find(scope_users_q, {
        "user_id": 1, "name": 1, "email": 1, "cedula": 1,
        "department_id": 1, "position": 1, "picture": 1, "_id": 0,
    })}
    depts = {d["department_id"]: d["name"] async for d in db.departments.find({}, {"department_id": 1, "name": 1, "_id": 0})}

    per_user: Dict[str, Dict[str, Any]] = {}
    per_dept_late: Dict[str, int] = {}
    per_dept_total: Dict[str, int] = {}
    total_ins = 0
    total_late = 0
    total_late_minor = 0
    total_late_major = 0
    total_late_major_pending = 0
    total_late_minutes = 0

    async for r in db.attendance.find(
        q,
        {"user_id": 1, "is_late": 1, "late_minutes": 1, "late_severity": 1,
         "requires_justification": 1, "justification": 1, "_id": 0},
    ):
        total_ins += 1
        uid = r.get("user_id")
        user = users.get(uid, {})
        dept_id = user.get("department_id") or "__none"
        per_dept_total[dept_id] = per_dept_total.get(dept_id, 0) + 1
        if r.get("is_late"):
            total_late += 1
            total_late_minutes += int(r.get("late_minutes") or 0)
            sev = r.get("late_severity") or ("late_major" if int(r.get("late_minutes") or 0) > 30 else "late_minor")
            if sev == "late_major":
                total_late_major += 1
                if r.get("requires_justification") and not r.get("justification"):
                    total_late_major_pending += 1
            else:
                total_late_minor += 1
            u = per_user.setdefault(uid, {
                "user_id": uid,
                "name": user.get("name", uid),
                "cedula": user.get("cedula"),
                "position": user.get("position"),
                "department_name": depts.get(user.get("department_id") or "", "Sin departamento"),
                "late_count": 0,
                "total_minutes": 0,
            })
            u["late_count"] += 1
            u["total_minutes"] += int(r.get("late_minutes") or 0)
            per_dept_late[dept_id] = per_dept_late.get(dept_id, 0) + 1

    top_late = sorted(per_user.values(),
                      key=lambda x: (x["late_count"], x["total_minutes"]),
                      reverse=True)[:5]

    dept_ranking = []
    for dept_id, total in per_dept_total.items():
        late = per_dept_late.get(dept_id, 0)
        dept_ranking.append({
            "department_id": None if dept_id == "__none" else dept_id,
            "department_name": depts.get(dept_id, "Sin departamento"),
            "total_ins": total,
            "late": late,
            "late_pct": round((late / total) * 100, 1) if total else 0,
        })
    dept_ranking.sort(key=lambda x: x["late_pct"], reverse=True)

    return {
        "days": days,
        "since": since.isoformat(),
        "generated_at": now_utc().isoformat(),
        "total_check_ins": total_ins,
        "total_late": total_late,
        "total_late_minor": total_late_minor,
        "total_late_major": total_late_major,
        "total_late_major_pending": total_late_major_pending,
        "late_pct": round((total_late / total_ins) * 100, 1) if total_ins else 0,
        "avg_late_minutes": round(total_late_minutes / total_late, 1) if total_late else 0,
        "top_late": top_late,
        "department_ranking": dept_ranking[:8],
    }


@api.get("/stats/dashboard")
async def stats_dashboard(user: Dict[str, Any] = Depends(require_roles("admin", "coordinador", "gerente", "director"))) -> Dict[str, Any]:
    scope: Dict[str, Any] = {}
    user_scope: Dict[str, Any] = {}
    nov_scope: Dict[str, Any] = {}
    if user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        scope["user_id"] = {"$in": team_ids}
        user_scope["user_id"] = {"$in": team_ids}
        nov_scope["user_id"] = {"$in": team_ids}
    total_users = await db.users.count_documents(user_scope)
    onboarded = await db.users.count_documents({**user_scope, "onboarded": True})
    local_now = now_utc().astimezone(APP_TZ)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today_in = await db.attendance.count_documents({**scope, "timestamp": {"$gte": start}, "type": "in"})
    today_late = await db.attendance.count_documents({**scope, "timestamp": {"$gte": start}, "type": "in", "is_late": True})
    today_late_major_pending = await db.attendance.count_documents({
        **scope,
        "timestamp": {"$gte": start},
        "type": "in",
        "late_severity": "late_major",
        "requires_justification": True,
        "$or": [{"justification": None}, {"justification": ""}],
    })
    pending_nov = await db.novelties.count_documents({**nov_scope, "status": "pending"})
    # attendance last 7 days
    series = []
    for i in range(6, -1, -1):
        day_start = start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        ins = await db.attendance.count_documents({**scope, "timestamp": {"$gte": day_start, "$lt": day_end}, "type": "in"})
        lates = await db.attendance.count_documents({**scope, "timestamp": {"$gte": day_start, "$lt": day_end}, "type": "in", "is_late": True})
        series.append({"date": day_start.astimezone(APP_TZ).strftime("%Y-%m-%d"),
                       "check_ins": ins, "late": lates})
    return {
        "total_users": total_users,
        "onboarded_users": onboarded,
        "check_ins_today": today_in,
        "late_today": today_late,
        "late_major_pending": today_late_major_pending,
        "pending_novelties": pending_nov,
        "series_7d": series,
    }


@api.get("/reports")
async def reports_list(from_date: Optional[str] = Query(None),
                       to_date: Optional[str] = Query(None),
                       user_id: Optional[str] = Query(None),
                       site_id: Optional[str] = Query(None),
                       user: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if user_id:
        q["user_id"] = user_id
    if site_id:
        q["site_id"] = site_id
    rng = _parse_date_range(from_date, to_date)
    if rng:
        q["timestamp"] = rng
    if user["role"] == "employee":
        q["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        team_ids = await supervisor_scope_ids(user)
        if user_id and user_id not in team_ids:
            return []
        q["user_id"] = {"$in": team_ids} if not user_id else user_id
    docs = await db.attendance.find(q, {"selfie_base64": 0}).sort("timestamp", -1).limit(5000).to_list(5000)
    return [strip_mongo_id(d) for d in docs]


@api.get("/reports/export")
async def reports_export(from_date: Optional[str] = Query(None),
                         to_date: Optional[str] = Query(None),
                         user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    q: Dict[str, Any] = {}
    rng = _parse_date_range(from_date, to_date)
    if rng:
        q["timestamp"] = rng
    if user["role"] == "employee":
        q["user_id"] = user["user_id"]
    elif user["role"] in LEADER_ROLES:
        q["user_id"] = {"$in": await supervisor_scope_ids(user)}
    users = {u["user_id"]: u async for u in db.users.find({}, {"user_id": 1, "name": 1, "email": 1, "cedula": 1})}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["record_id", "user_id", "name", "cedula", "type", "timestamp_utc",
                "timestamp_local", "site_id", "within_geofence", "is_late", "late_minutes",
                "late_severity", "requires_justification", "justification"])
    async for r in db.attendance.find(q).sort("timestamp", -1):
        u = users.get(r.get("user_id"), {})
        ts = r.get("timestamp")
        if isinstance(ts, datetime):
            ts_local = ts.astimezone(APP_TZ).strftime("%Y-%m-%d %H:%M:%S")
            ts_utc = ts.astimezone(timezone.utc).isoformat()
        else:
            ts_local = str(ts)
            ts_utc = str(ts)
        w.writerow([r.get("record_id"), r.get("user_id"), u.get("name"), u.get("cedula"),
                    r.get("type"), ts_utc, ts_local, r.get("site_id"),
                    r.get("within_geofence"), r.get("is_late"), r.get("late_minutes"),
                    r.get("late_severity") or "", r.get("requires_justification") or False,
                    r.get("justification") or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=asistencia_report.csv"})


# ==================================================================
# REPORTE MATRICIAL (3 endpoints)
# ==================================================================
from matrix_report import build_matrix, export_xlsx, export_pdf  # noqa: E402


async def _matrix_scope_ids(user: Dict[str, Any]) -> Optional[List[str]]:
    role = user.get("role")
    if role == "employee":
        return [user["user_id"]]
    if role in LEADER_ROLES:
        return await supervisor_scope_ids(user)
    return None  # admin → sin restricción


def _parse_list_query(val: Optional[str]) -> Optional[List[str]]:
    if not val:
        return None
    out = [v for v in val.split(",") if v.strip()]
    return out or None


@api.get("/reports/matrix")
async def reports_matrix(from_date: str = Query(...),
                         to_date: str = Query(...),
                         department_ids: Optional[str] = Query(None),
                         user_ids: Optional[str] = Query(None),
                         site_id: Optional[str] = Query(None),
                         schedule_id: Optional[str] = Query(None),
                         user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    scope = await _matrix_scope_ids(user)
    return await build_matrix(
        db, from_date, to_date,
        scope_user_ids=scope,
        department_ids=_parse_list_query(department_ids),
        user_ids=_parse_list_query(user_ids),
        site_id=site_id or None,
        schedule_id=schedule_id or None,
    )


@api.get("/reports/matrix/export.xlsx")
async def reports_matrix_xlsx(from_date: str = Query(...),
                              to_date: str = Query(...),
                              department_ids: Optional[str] = Query(None),
                              user_ids: Optional[str] = Query(None),
                              site_id: Optional[str] = Query(None),
                              schedule_id: Optional[str] = Query(None),
                              user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    scope = await _matrix_scope_ids(user)
    matrix = await build_matrix(
        db, from_date, to_date,
        scope_user_ids=scope,
        department_ids=_parse_list_query(department_ids),
        user_ids=_parse_list_query(user_ids),
        site_id=site_id or None,
        schedule_id=schedule_id or None,
    )
    xlsx_bytes = export_xlsx(matrix)
    filename = f"matriz_asistencia_{from_date}_a_{to_date}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api.get("/reports/matrix/export.pdf")
async def reports_matrix_pdf(from_date: str = Query(...),
                             to_date: str = Query(...),
                             department_ids: Optional[str] = Query(None),
                             user_ids: Optional[str] = Query(None),
                             site_id: Optional[str] = Query(None),
                             schedule_id: Optional[str] = Query(None),
                             user: Dict[str, Any] = Depends(get_current_user)) -> StreamingResponse:
    scope = await _matrix_scope_ids(user)
    matrix = await build_matrix(
        db, from_date, to_date,
        scope_user_ids=scope,
        department_ids=_parse_list_query(department_ids),
        user_ids=_parse_list_query(user_ids),
        site_id=site_id or None,
        schedule_id=schedule_id or None,
    )
    settings = await db.settings.find_one({"_id": "company"}) or {}
    pdf_bytes = export_pdf(matrix,
                           company_name=settings.get("company_name") or "Mega Soft",
                           logo_base64=settings.get("logo_base64"))
    filename = f"matriz_asistencia_{from_date}_a_{to_date}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================================================================
# ONBOARDING (1 endpoint)
# ==================================================================
@api.post("/onboarding/selfie")
async def onboarding_selfie(payload: SelfieIn,
                            user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    updates: Dict[str, Any] = {"selfie_base64": payload.selfie_base64, "onboarded": True}
    if payload.face_descriptor is not None:
        updates["face_descriptor"] = payload.face_descriptor
    await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
    return {"ok": True}


# ------------------------------------------------------------------
# Wire router + CORS
# ------------------------------------------------------------------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
