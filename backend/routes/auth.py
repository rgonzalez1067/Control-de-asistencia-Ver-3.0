"""Endpoints de autenticación (login/register/me/logout/change-password/change-pin/reset).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
from deps import (
    api, db, get_current_user, require_roles,
    now_utc, new_id,
    hash_password, verify_password, create_access_token,
    enrich_user_with_permissions, validate_password_policy,
    LoginIn, RegisterIn, ChangePasswordIn, ChangePinIn, ResetPasswordIn,
    HTTPException, Depends, Response,
    Any, Dict,
)


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
