"""Endpoints de autenticación (login/register/me/logout/change-password/change-pin/reset).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
from deps import (
    api, db, get_current_user, require_roles,
    now_utc, new_id,
    hash_password, verify_password, create_access_token,
    enrich_user_with_permissions, validate_password_policy,
    LoginIn, RegisterIn, ChangePasswordIn, ChangePinIn, ResetPasswordIn,
    HTTPException, Depends, Response, Request,
    Any, Dict,
    limiter, audit_log,
)


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
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        await audit_log("login_failed", request, email=email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    token = create_access_token(user["user_id"], user["role"])
    await audit_log("login_success", request, user_id=user["user_id"], email=email,
                    extra={"role": user.get("role")})
    return {"token": token, "user": await enrich_user_with_permissions(user)}


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
from datetime import timedelta
from email_service import send_email, render_reset_email, is_configured as smtp_configured

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
    await db.users.update_one(
        {"user_id": doc["user_id"]},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_updated_at": now_utc(),
            "password_updated_by_user": True,
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
