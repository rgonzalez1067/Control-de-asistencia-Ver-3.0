"""Endpoints de autenticación (login/register/me/logout/change-password/change-pin/reset).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
Extendido con 2FA por correo (feb-2026): cuando el admin activa `enable_email_2fa`
en Ajustes, el login pasa a ser un flujo de 2 pasos:
  1) POST /auth/login → si credenciales OK, se emite un `otp_token` temporal y
     se envía un código de 6 dígitos al correo del usuario.
  2) POST /auth/verify-otp → intercambia `otp_token` + `code` por el JWT final.
"""
import hashlib
import secrets as _secrets
from deps import (
    api, db, get_current_user, require_roles,
    now_utc, new_id,
    hash_password, verify_password, create_access_token,
    enrich_user_with_permissions, validate_password_policy,
    password_is_reused, password_expired,
    PASSWORD_HISTORY_SIZE, LOGIN_MAX_FAILED, LOGIN_LOCKOUT_MINUTES,
    JWT_SECRET, JWT_ALGORITHM,
    LoginIn, RegisterIn, ChangePasswordIn, ChangePinIn, ResetPasswordIn,
    HTTPException, Depends, Response, Request,
    Any, Dict,
    limiter, audit_log,
    datetime, timezone, timedelta,
)
import jwt as _jwt
from security_config import get_security_config
from email_service import send_email, render_reset_email, is_configured as smtp_configured


@api.get("/auth/needs-bootstrap")
async def auth_needs_bootstrap() -> Dict[str, bool]:
    """True si no existe ningún usuario admin (para primer setup)."""
    admin = await db.users.find_one({"role": "admin"})
    return {"needs_bootstrap": admin is None}


@api.post("/auth/register")
@limiter.limit("3/minute")
async def auth_register(request: Request, payload: RegisterIn, response: Response) -> Dict[str, Any]:
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
    await audit_log("register_bootstrap_admin", request, user_id=user["user_id"], email=email)
    return {"token": token, "user": await enrich_user_with_permissions(user)}


@api.post("/auth/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, payload: LoginIn, response: Response) -> Dict[str, Any]:
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})

    # Configuración dinámica de seguridad
    cfg = await get_security_config(db)
    max_failed = int(cfg["max_login_attempts"])
    lockout_min = int(cfg["lockout_minutes"])
    max_age_days = int(cfg["password_expiration_days"])

    # 1) Cuenta bloqueada por intentos fallidos consecutivos
    if user:
        locked_until = user.get("locked_until")
        if isinstance(locked_until, datetime):
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now_utc():
                remaining = int((locked_until - now_utc()).total_seconds() / 60) + 1
                await audit_log("login_locked", request, email=email, extra={"minutes_remaining": remaining})
                raise HTTPException(
                    status_code=423,
                    detail=f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {remaining} minuto(s) o contacta al Administrador.",
                )

    # 2) Verificación de credenciales
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        if user:
            fails = int(user.get("failed_login_attempts", 0)) + 1
            upd: Dict[str, Any] = {"failed_login_attempts": fails}
            if fails >= max_failed:
                upd["locked_until"] = now_utc() + timedelta(minutes=lockout_min)
                upd["failed_login_attempts"] = 0
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
            if "locked_until" in upd:
                await audit_log("login_locked_out", request, email=email,
                                extra={"lockout_minutes": lockout_min})
                raise HTTPException(
                    status_code=423,
                    detail=f"Cuenta bloqueada por {max_failed} intentos fallidos. Espera {lockout_min} minutos o contacta al Administrador.",
                )
            await audit_log("login_failed", request, email=email,
                            extra={"failed_attempts": fails})
        else:
            await audit_log("login_failed", request, email=email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    # 3) Credenciales OK — reset counters
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"failed_login_attempts": 0, "locked_until": None}},
    )
    user["failed_login_attempts"] = 0
    user["locked_until"] = None

    # 4) 2FA por correo — si está activo Y el usuario tiene email, se emite un
    #    reto OTP. Usuarios `kiosk` quedan exentos (login mecánico de dispositivo).
    if cfg["enable_email_2fa"] and (user.get("role") != "kiosk") and user.get("email"):
        challenge = await _create_otp_challenge(request, user, cfg)
        return {
            "requires_otp": True,
            "otp_token": challenge["otp_token"],
            "email_masked": _mask_email(user["email"]),
            "expires_in_minutes": int(cfg["otp_expiration_minutes"]),
            "delivery": challenge["delivery"],
        }

    # 5) Sin 2FA — emite JWT directamente
    return await _finalize_login(request, user, max_age_days)


async def _finalize_login(request: Request, user: Dict[str, Any],
                          max_age_days: int) -> Dict[str, Any]:
    """Emite el JWT final y actualiza contadores/flags. Común al flujo sin 2FA
    y al flujo con verificación OTP exitosa."""
    must_change = bool(user.get("must_change_password")) or password_expired(user, max_days=max_age_days)
    if password_expired(user, max_days=max_age_days) and not user.get("must_change_password"):
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"must_change_password": True}})
        user["must_change_password"] = True
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_login_at": now_utc()}})
    token = create_access_token(user["user_id"], user["role"])
    await audit_log("login_success", request, user_id=user["user_id"], email=user.get("email"),
                    extra={"role": user.get("role"), "must_change_password": must_change})
    return {"token": token, "user": await enrich_user_with_permissions(user),
            "must_change_password": must_change}


# --------------------------------------------------------------------------
# 2FA por correo — helpers y endpoint /auth/verify-otp
# --------------------------------------------------------------------------
_OTP_JWT_TYPE = "otp_challenge"


def _mask_email(email: str) -> str:
    """Enmascara el correo para mostrar en el desafío: `j***@dominio.com`."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _render_otp_email(name: str, code: str, minutes_valid: int) -> Dict[str, str]:
    text = (
        f"Hola {name},\n\n"
        f"Tu código de verificación (2FA) para acceder a Megasoft Asistencia es:\n\n"
        f"    {code}\n\n"
        f"Es válido por {minutes_valid} minuto(s). Si tú no intentaste iniciar sesión, "
        "cambia tu contraseña de inmediato y notifica al administrador.\n\n"
        "— Megasoft Asistencia"
    )
    html = (
        '<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f6f7fb;padding:24px">'
        '<table cellpadding="0" cellspacing="0" style="max-width:520px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">'
        '<tr><td style="padding:20px 24px;background:#0f172a;color:#fff;font-size:16px;font-weight:600">'
        "Megasoft Asistencia · Verificación 2FA</td></tr>"
        f'<tr><td style="padding:24px"><p style="margin:0 0 12px;color:#0f172a">Hola {name},</p>'
        '<p style="margin:0 0 12px;color:#475569">Ingresa este código para completar tu inicio de sesión:</p>'
        f'<p style="text-align:center;font-size:32px;letter-spacing:8px;font-weight:800;color:#0f172a;background:#f1f5f9;border-radius:12px;padding:14px 0;margin:12px 0">{code}</p>'
        f'<p style="margin:0;color:#64748b;font-size:12px">El código es válido por <b>{minutes_valid} minuto(s)</b>. Si no fuiste tú, cambia tu contraseña de inmediato.</p>'
        "</td></tr></table></body></html>"
    )
    return {"text": text, "html": html}


async def _create_otp_challenge(request: Request, user: Dict[str, Any],
                                cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Crea el reto OTP, envía el correo y devuelve el JWT temporal."""
    code = f"{_secrets.randbelow(1_000_000):06d}"
    ttl_min = int(cfg["otp_expiration_minutes"])
    max_attempts = int(cfg["otp_max_attempts"])
    challenge_id = new_id("otp", 16)
    await db.otp_challenges.insert_one({
        "challenge_id": challenge_id,
        "user_id": user["user_id"],
        "email": user["email"],
        "otp_hash": _hash_otp(code),
        "attempts": 0,
        "max_attempts": max_attempts,
        "expires_at": now_utc() + timedelta(minutes=ttl_min),
        "created_at": now_utc(),
        "consumed_at": None,
        "ip": request.client.host if request.client else None,
    })
    # Token temporal — sólo autoriza a llamar /auth/verify-otp.
    otp_token = _jwt.encode(
        {
            "type": _OTP_JWT_TYPE,
            "cid": challenge_id,
            "sub": user["user_id"],
            "iat": int(now_utc().timestamp()),
            "exp": now_utc() + timedelta(minutes=ttl_min + 1),
        },
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )
    body = _render_otp_email(
        name=user.get("name") or "Colaborador",
        code=code,
        minutes_valid=ttl_min,
    )
    send_result = await send_email(
        user["email"], "Código de verificación 2FA · Megasoft Asistencia",
        body["text"], body["html"],
    )
    await audit_log("otp_challenge_issued", request, user_id=user["user_id"],
                    email=user["email"], extra={"delivery": send_result})
    return {
        "otp_token": otp_token,
        "delivery": {
            "sent": bool(send_result.get("sent")),
            "reason": send_result.get("reason"),
        },
    }


@api.post("/auth/verify-otp")
@limiter.limit("10/minute")
async def auth_verify_otp(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Consume un OTP y emite el JWT final. Payload: `{otp_token, code}`."""
    otp_token = ((payload or {}).get("otp_token") or "").strip()
    code = ((payload or {}).get("code") or "").strip()
    if not otp_token or not code:
        raise HTTPException(status_code=400, detail="Faltan datos (token y código)")
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="El código debe ser de 6 dígitos")
    try:
        claims = _jwt.decode(otp_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El código expiró — vuelve a iniciar sesión")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token de verificación inválido")
    if claims.get("type") != _OTP_JWT_TYPE:
        raise HTTPException(status_code=401, detail="Token de verificación inválido")
    challenge_id = claims.get("cid")
    challenge = await db.otp_challenges.find_one({"challenge_id": challenge_id})
    if not challenge:
        raise HTTPException(status_code=401, detail="Desafío no encontrado")
    if challenge.get("consumed_at"):
        raise HTTPException(status_code=401, detail="Este código ya fue utilizado")
    exp = challenge.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now_utc():
            raise HTTPException(status_code=401, detail="El código expiró — vuelve a iniciar sesión")

    if _hash_otp(code) != challenge.get("otp_hash"):
        new_attempts = int(challenge.get("attempts", 0)) + 1
        max_attempts = int(challenge.get("max_attempts") or 3)
        if new_attempts >= max_attempts:
            await db.otp_challenges.update_one(
                {"challenge_id": challenge_id},
                {"$set": {"attempts": new_attempts, "consumed_at": now_utc(),
                          "invalidated_reason": "max_attempts"}},
            )
            await audit_log("otp_verify_locked", request, user_id=claims.get("sub"),
                            extra={"attempts": new_attempts})
            raise HTTPException(
                status_code=401,
                detail="Superaste los intentos permitidos. Vuelve a iniciar sesión.",
            )
        await db.otp_challenges.update_one(
            {"challenge_id": challenge_id},
            {"$set": {"attempts": new_attempts}},
        )
        remaining = max_attempts - new_attempts
        await audit_log("otp_verify_failed", request, user_id=claims.get("sub"),
                        extra={"attempts": new_attempts, "remaining": remaining})
        raise HTTPException(
            status_code=401,
            detail=f"Código incorrecto. Te quedan {remaining} intento(s).",
        )

    # Éxito — consumir el reto y emitir el JWT
    await db.otp_challenges.update_one(
        {"challenge_id": challenge_id},
        {"$set": {"consumed_at": now_utc()}},
    )
    user = await db.users.find_one({"user_id": claims.get("sub")})
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    cfg = await get_security_config(db)
    await audit_log("otp_verify_success", request, user_id=user["user_id"], email=user.get("email"))
    return await _finalize_login(request, user, int(cfg["password_expiration_days"]))


@api.get("/auth/me")
async def auth_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return await enrich_user_with_permissions(user)


@api.post("/auth/logout")
async def auth_logout(response: Response) -> Dict[str, bool]:
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.post("/auth/change-password")
async def auth_change_password(payload: ChangePasswordIn,
                               user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    if not verify_password(payload.old_password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta a la actual")
    validate_password_policy(payload.new_password)
    # Historial: incluir la clave actual + últimas N. Rechazar reutilización.
    cfg = await get_security_config(db)
    history_size = int(cfg["password_history_size"])
    history = [user.get("password_hash", "")] + list(user.get("password_history") or [])
    if password_is_reused(payload.new_password, history, history_size=history_size):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes reutilizar tus últimas {history_size} contraseñas.",
        )
    new_hash = hash_password(payload.new_password)
    new_history = ([user.get("password_hash", "")] + list(user.get("password_history") or []))[:history_size]
    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"password_hash": new_hash,
                                        "password_updated_at": now_utc(),
                                        "password_history": new_history,
                                        "must_change_password": False,
                                        "failed_login_attempts": 0,
                                        "locked_until": None}})
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


@api.post("/auth/reset-password")
async def auth_reset_password(request: Request, payload: ResetPasswordIn,
                              user: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, bool]:
    res = await db.users.update_one(
        {"user_id": payload.user_id},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "must_change_password": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    await audit_log("admin_reset_password", request, user_id=user["user_id"], email=user.get("email"),
                    extra={"target_user_id": payload.user_id})
    return {"ok": True}


@api.post("/admin/reset-all-passwords")
async def admin_reset_all_passwords(
    request: Request,
    payload: Dict[str, Any],
    user: Dict[str, Any] = Depends(require_roles("admin")),
) -> Dict[str, Any]:
    """Resetea la contraseña de TODOS los usuarios no-admin al valor indicado y
    marca `must_change_password=true` para forzar cambio al primer login.
    Payload: {"new_password": "Mega2026*"}

    Requiere doble autenticación: JWT admin + header X-Admin-Token (bóveda)."""
    from routes.admin import _verify_vault_token
    provided_vault = request.headers.get("X-Admin-Token", "")
    if not await _verify_vault_token(provided_vault):
        raise HTTPException(status_code=403,
                            detail="Se requiere el token de bóveda administrativa (X-Admin-Token)")
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
    await audit_log("admin_reset_all_passwords", request, user_id=user["user_id"],
                    email=user.get("email"), extra={"affected": res.modified_count})
    return {"ok": True, "affected": res.modified_count}



# --------------------------------------------------------------------------
# Recuperación de contraseña (feb-2026) — flujo público de auto-servicio
# --------------------------------------------------------------------------
import os
import secrets

RESET_TOKEN_TTL_MIN = 30


@api.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def auth_forgot_password(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Solicita un enlace de recuperación. Respuesta idempotente: siempre
    devuelve `{ok: True}` — nunca revela si el email/cédula existe (evita
    enumeración). El envío real del correo ocurre en background si SMTP está
    configurado."""
    identifier = ((payload or {}).get("identifier") or "").strip().lower()
    if not identifier:
        raise HTTPException(status_code=400, detail="Debes indicar tu correo o cédula")
    user = await db.users.find_one({"$or": [
        {"email": identifier},
        {"cedula": identifier},
    ]})
    if user and user.get("active") is not False:
        token = secrets.token_urlsafe(48)
        await db.password_reset_tokens.insert_one({
            "token": token,
            "user_id": user["user_id"],
            "email": user.get("email"),
            "created_at": now_utc(),
            "expires_at": now_utc() + timedelta(minutes=RESET_TOKEN_TTL_MIN),
            "used_at": None,
            "ip": request.client.host if request.client else None,
        })
        base = os.environ.get("APP_PUBLIC_URL") or str(request.base_url).rstrip("/")
        link = f"{base}/reset-password?token={token}"
        body = render_reset_email(
            name=user.get("name") or user.get("first_name") or "Colaborador",
            link=link,
            minutes_valid=RESET_TOKEN_TTL_MIN,
        )
        await send_email(user["email"], "Restablece tu contraseña · Megasoft Asistencia",
                         body["text"], body["html"])
        await audit_log("password_reset_requested", request, user_id=user["user_id"],
                        email=user.get("email"))
    return {"ok": True, "smtp_configured": smtp_configured()}


@api.post("/auth/reset-password-with-token")
@limiter.limit("10/minute")
async def auth_reset_password_with_token(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Consume un token de recuperación y establece la nueva contraseña."""
    token = ((payload or {}).get("token") or "").strip()
    new_password = (payload or {}).get("new_password") or ""
    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Faltan datos (token y contraseña nueva)")
    validate_password_policy(new_password)
    doc = await db.password_reset_tokens.find_one({"token": token})
    if not doc:
        raise HTTPException(status_code=400, detail="Enlace inválido")
    if doc.get("used_at"):
        raise HTTPException(status_code=400, detail="Este enlace ya fue utilizado")
    exp = doc.get("expires_at")
    if exp and exp < now_utc():
        raise HTTPException(status_code=400, detail="El enlace expiró — solicita uno nuevo")
    user = await db.users.find_one({"user_id": doc["user_id"]})
    if not user or user.get("active") is False:
        raise HTTPException(status_code=400, detail="Usuario no válido")
    cfg = await get_security_config(db)
    history_size = int(cfg["password_history_size"])
    history = [user.get("password_hash", "")] + list(user.get("password_history") or [])
    if password_is_reused(new_password, history, history_size=history_size):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes reutilizar tus últimas {history_size} contraseñas.",
        )
    new_history = ([user.get("password_hash", "")] + list(user.get("password_history") or []))[:history_size]
    await db.users.update_one(
        {"user_id": doc["user_id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_updated_at": now_utc(),
            "password_updated_by_user": True,
            "password_history": new_history,
            "must_change_password": False,
            "failed_login_attempts": 0,
            "locked_until": None,
        }},
    )
    await db.password_reset_tokens.update_one(
        {"token": token}, {"$set": {"used_at": now_utc()}},
    )
    # Invalida cualquier otro token pendiente del mismo usuario.
    await db.password_reset_tokens.update_many(
        {"user_id": doc["user_id"], "used_at": None, "token": {"$ne": token}},
        {"$set": {"used_at": now_utc()}},
    )
    await audit_log("password_reset_completed", request, user_id=user["user_id"],
                    email=user.get("email"))
    return {"ok": True}
