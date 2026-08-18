"""Endpoints RBAC: gestión de Perfiles de Acceso (Access Profiles).

Migrado desde server.py durante la Fase A · Iteración 3 (feb-2026).
"""
from deps import (
    api, db, require_roles,
    now_utc, new_id, strip_mongo_id,
    MENU_CATALOG, MENU_KEYS,
    AccessProfileIn, AssignProfileIn, AssignProfileToDeptIn,
    HTTPException, Depends,
    Any, Dict, List,
)


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
