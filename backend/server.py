"""
MegaSoft Asistencia — FastAPI Backend
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
import uuid
import math
import jwt
import bcrypt
import logging
import secrets
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Any, Dict, Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, JSONResponse
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

app = FastAPI(title="MegaSoft Asistencia API", version="0.1.0")
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
    return user


def require_roles(*roles: str):
    async def _dep(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="No autorizado")
        return user
    return _dep


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
    new_password: str


class ResetPasswordIn(BaseModel):
    user_id: str
    new_password: str


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
    type: Literal["vacation", "leave", "medical", "permission", "other"]
    start_date: str
    end_date: str
    reason: Optional[str] = None
    user_id: Optional[str] = None  # admin/supervisor can create for others


class NoveltyDecideIn(BaseModel):
    novelty_ids: List[str]
    decision: Literal["approved", "rejected"]
    comment: Optional[str] = None


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
    logger.info("Startup completo.")


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
    return {"token": token, "user": sanitize_user(user)}


@api.post("/auth/login")
async def auth_login(payload: LoginIn, response: Response) -> Dict[str, Any]:
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_access_token(user["user_id"], user["role"])
    return {"token": token, "user": sanitize_user(user)}


@api.get("/auth/me")
async def auth_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return sanitize_user(user)


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
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"password_hash": hash_password(payload.new_password)}})
    return {"ok": True}


@api.post("/auth/reset-password")
async def auth_reset_password(payload: ResetPasswordIn,
                              _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.users.update_one(
        {"user_id": payload.user_id},
        {"$set": {"password_hash": hash_password(payload.new_password)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


# ==================================================================
# USERS (8 endpoints)
# ==================================================================
@api.get("/users")
async def users_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.users.find({}, {"password_hash": 0, "pin_code_hash": 0,
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
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
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
         "Analista", "", "", "", "", "Temporal2026*", "1234"],
        ["mrodriguez@empresa.com", "María Rodríguez", "23456789", "supervisor",
         "Coordinadora", "", "", "", "", "", "5678"],
        ["cgomez@empresa.com", "Carlos Gómez", "34567890", "employee",
         "Técnico Soporte", "", "", "user_abc123", "sched_xyz789", "", ""],
    ]
    for row in ejemplos:
        ws2.append(row)

    # Nota / leyenda al pie de la pestaña Ejemplos
    ws2.append([])
    ws2.append(["NOTAS:"])
    ws2["A" + str(ws2.max_row)].font = Font(bold=True, color="B45309")
    notas = [
        "• Sólo email y name son obligatorios. El resto puede ir vacío.",
        "• role: employee | supervisor | admin (default: employee).",
        "• Si el email ya existe → se ACTUALIZAN sólo los campos con valor (no sobrescribe con vacío).",
        "• Si el email NO existe → se INSERTA un nuevo empleado.",
        "• password: sólo se aplica al crear. Si se omite, se genera uno aleatorio.",
        "• kiosk_pin: 4 dígitos numéricos para el modo kiosco (marca con PIN).",
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
    for i, row in enumerate(rows, start=2):
        if row is None or all(v is None for v in row):
            continue
        try:
            email = (_get(row, "email") or "").lower()
            name = _get(row, "name")
            if not email or not name:
                errors.append(f"Fila {i}: email/name requerido")
                continue

            payload_fields = {
                "cedula": _get(row, "cedula"),
                "role": _get(row, "role"),
                "position": _get(row, "position"),
                "department_id": _get(row, "department_id"),
                "site_id": _get(row, "site_id"),
                "supervisor_id": _get(row, "supervisor_id"),
                "schedule_id": _get(row, "schedule_id"),
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
        except Exception as e:  # noqa: BLE001
            errors.append(f"Fila {i}: {e}")
    return {"created": created, "updated": updated, "errors": errors}


# ==================================================================
# SETTINGS (2 endpoints)
# ==================================================================
@api.get("/settings")
async def settings_get() -> Dict[str, Any]:
    doc = await db.settings.find_one({"_id": "company"}) or {"_id": "company"}
    # normaliza: reemplaza _id por id string en respuesta
    doc["id"] = str(doc.pop("_id"))
    return doc


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
@api.get("/schedules")
async def schedules_list(_: Dict[str, Any] = Depends(get_current_user)) -> List[Dict[str, Any]]:
    docs = await db.schedules.find({}).to_list(500)
    return [strip_mongo_id(d) for d in docs]


@api.post("/schedules")
async def schedules_create(payload: ScheduleIn,
                           _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    doc = payload.model_dump()
    doc["schedule_id"] = new_id("sch", 10)
    doc["created_at"] = now_utc()
    await db.schedules.insert_one(doc)
    return strip_mongo_id(doc)


@api.put("/schedules/{schedule_id}")
async def schedules_update(schedule_id: str, payload: ScheduleIn,
                           _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    res = await db.schedules.update_one({"schedule_id": schedule_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    doc = await db.schedules.find_one({"schedule_id": schedule_id})
    return strip_mongo_id(doc)


@api.delete("/schedules/{schedule_id}")
async def schedules_delete(schedule_id: str,
                           _: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.schedules.delete_one({"schedule_id": schedule_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    return {"ok": True}


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
                          user: Dict[str, Any] = Depends(require_roles("admin", "supervisor"))) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"timestamp": {"$gte": now_utc() - timedelta(days=days)}}
    if user["role"] == "supervisor":
        team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
        team_ids = [t["user_id"] for t in team]
        query["user_id"] = {"$in": team_ids}
    docs = await db.attendance.find(query, {"selfie_base64": 0}).sort("timestamp", -1).limit(1000).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/attendance/justify")
async def attendance_justify(payload: JustifyIn,
                             user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    query = {"record_id": payload.record_id}
    if user["role"] not in {"admin", "supervisor"}:
        query["user_id"] = user["user_id"]
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
    elif user["role"] == "supervisor":
        team = await db.users.find({"supervisor_id": user["user_id"]}, {"user_id": 1}).to_list(1000)
        team_ids = [t["user_id"] for t in team] + [user["user_id"]]
        q["user_id"] = {"$in": team_ids}
    docs = await db.novelties.find(q).sort("created_at", -1).to_list(1000)
    return [strip_mongo_id(d) for d in docs]


@api.post("/novelties")
async def novelties_create(payload: NoveltyIn,
                           user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    target = payload.user_id or user["user_id"]
    if target != user["user_id"] and user["role"] not in {"admin", "supervisor"}:
        raise HTTPException(status_code=403, detail="No autorizado")
    doc = {
        "novelty_id": new_id("nv", 12),
        "user_id": target,
        "type": payload.type,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
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
    if user["role"] not in {"admin", "supervisor"}:
        q["user_id"] = user["user_id"]
        q["status"] = "pending"
    res = await db.novelties.delete_one(q)
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    return {"ok": True}


@api.post("/novelties/bulk-decide")
async def novelties_bulk_decide(payload: NoveltyDecideIn,
                                user: Dict[str, Any] = Depends(require_roles("admin", "supervisor"))) -> Dict[str, int]:
    res = await db.novelties.update_many(
        {"novelty_id": {"$in": payload.novelty_ids}, "status": "pending"},
        {"$set": {"status": payload.decision, "decided_at": now_utc(),
                  "decided_by": user["user_id"], "decision_comment": payload.comment}},
    )
    return {"updated": res.modified_count}


# ==================================================================
# STATS / REPORTS (3 endpoints)
# ==================================================================
@api.get("/stats/executive")
async def stats_executive(days: int = 30,
                          _: Dict[str, Any] = Depends(require_roles("admin", "supervisor"))) -> Dict[str, Any]:
    """Métricas ejecutivas: top tardanzas, ranking por depto, promedio minutos tarde."""
    since = now_utc() - timedelta(days=days)
    q = {"timestamp": {"$gte": since}, "type": "in"}

    users = {u["user_id"]: u async for u in db.users.find({}, {
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
async def stats_dashboard(_: Dict[str, Any] = Depends(require_roles("admin", "supervisor"))) -> Dict[str, Any]:
    total_users = await db.users.count_documents({})
    onboarded = await db.users.count_documents({"onboarded": True})
    local_now = now_utc().astimezone(APP_TZ)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today_in = await db.attendance.count_documents({"timestamp": {"$gte": start}, "type": "in"})
    today_late = await db.attendance.count_documents({"timestamp": {"$gte": start}, "type": "in", "is_late": True})
    today_late_major_pending = await db.attendance.count_documents({
        "timestamp": {"$gte": start},
        "type": "in",
        "late_severity": "late_major",
        "requires_justification": True,
        "$or": [{"justification": None}, {"justification": ""}],
    })
    pending_nov = await db.novelties.count_documents({"status": "pending"})
    # attendance last 7 days
    series = []
    for i in range(6, -1, -1):
        day_start = start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        ins = await db.attendance.count_documents({"timestamp": {"$gte": day_start, "$lt": day_end}, "type": "in"})
        lates = await db.attendance.count_documents({"timestamp": {"$gte": day_start, "$lt": day_end}, "type": "in", "is_late": True})
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
                       _: Dict[str, Any] = Depends(require_roles("admin", "supervisor"))) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if user_id:
        q["user_id"] = user_id
    if site_id:
        q["site_id"] = site_id
    rng = _parse_date_range(from_date, to_date)
    if rng:
        q["timestamp"] = rng
    docs = await db.attendance.find(q, {"selfie_base64": 0}).sort("timestamp", -1).limit(5000).to_list(5000)
    return [strip_mongo_id(d) for d in docs]


@api.get("/reports/export")
async def reports_export(from_date: Optional[str] = Query(None),
                         to_date: Optional[str] = Query(None),
                         _: Dict[str, Any] = Depends(require_roles("admin", "supervisor"))) -> StreamingResponse:
    q: Dict[str, Any] = {}
    rng = _parse_date_range(from_date, to_date)
    if rng:
        q["timestamp"] = rng
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
