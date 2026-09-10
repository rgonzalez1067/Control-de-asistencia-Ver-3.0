"""Endpoints del Kiosco: desbloqueo (password/rostro), sesiones, verificación PIN,
   marcaje desde kiosco, re-enrolamiento de rostro.

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
import math as _math
import json as _json
import jwt

from deps import (
    api, db, require_roles,
    APP_TZ, now_utc, new_id,
    JWT_SECRET, JWT_ALGORITHM,
    verify_password,
    KioskUnlockIn, KioskFaceUnlockIn, KioskPinIn, KioskAttendanceIn,
    HTTPException, Depends, Request, Form,
    Any, Dict, List, Optional,
    timezone, timedelta,
)


# ---- Kiosk Sessions (1 activo por sede) ---------------------------
# TTL: se considera "activo" si el heartbeat es reciente (< 5 min).
KIOSK_SESSION_TTL_MIN = 5


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


def _find_best_face_matches(desc: List[float], admins: List[Dict[str, Any]]):
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
    return best, second


async def _check_kiosk_reopen_permission(request: Request, site_id: str) -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return False
    token = auth.split(" ", 1)[1].strip()
    try:
        payload_jwt = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = payload_jwt.get("sub")
        if uid:
            requester = await db.users.find_one({"user_id": uid})
            return bool(requester and requester.get("role") == "kiosk" and requester.get("site_id") == site_id)
    except jwt.PyJWTError:
        pass
    return False


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

    best, second = _find_best_face_matches(desc, admins)
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
    """Lista pública de sedes para el selector del Kiosco (no requiere sesión)."""
    docs = await db.sites.find({}, {"site_id": 1, "name": 1, "address": 1, "_id": 0}).to_list(500)
    docs.sort(key=lambda s: (s.get("name") or "").lower())
    return docs


@api.get("/kiosk/roster", include_in_schema=False)
async def kiosk_roster(
    current_user: Dict[str, Any] = Depends(require_roles("kiosk", "admin")),
) -> List[Dict[str, Any]]:
    role = current_user.get("role")
    kiosk_site = current_user.get("site_id")
    query: Dict[str, Any] = {"onboarded": True}
###    if role == "kiosk" and kiosk_site:
###        query["site_id"] = kiosk_site

    docs = await db.users.find(
        query,
        {
            "user_id": 1,
            "name": 1,
            "site_id": 1,
            "selfie_base64": 1,
            "face_descriptor": 1,
            "_id": 0,
        },
    ).sort("name",1).to_list(5000)
    return docs


@api.post("/kiosk/session/open", include_in_schema=False)
async def kiosk_session_open(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
    site_id = (payload or {}).get("site_id")
    if not site_id:
        raise HTTPException(status_code=400, detail="Falta site_id")
    site = await db.sites.find_one({"site_id": site_id})
    if not site:
        raise HTTPException(status_code=404, detail="Sede no registrada")

    force_from_kiosk_user = await _check_kiosk_reopen_permission(request, site_id)
    cutoff = now_utc() - timedelta(minutes=KIOSK_SESSION_TTL_MIN)
    existing = await db.kiosk_sessions.find_one({
        "site_id": site_id,
        "closed_at": None,
        "last_heartbeat": {"$gte": cutoff},
    })
    if existing:
        if force_from_kiosk_user:
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

    # Lazy import para evitar ciclo (routes/attendance.py importa desde deps → server).
    from routes.attendance import _register_attendance
    return await _register_attendance(user, effective_type, payload.latitude, payload.longitude,
                                      payload.site_id, payload.selfie_base64, method="kiosk")


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
        try:
            updates["face_descriptor"] = _json.loads(face_descriptor)
        except Exception:
            pass
    await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
    return {"ok": True}
