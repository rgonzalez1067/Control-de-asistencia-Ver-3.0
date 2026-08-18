"""Endpoints de Usuarios (CRUD + importación Excel + selfie + PIN + foto).

Migrado desde server.py durante la Fase A · Iteración 4 (feb-2026).
Cierra la Fase A: `server.py` queda por debajo de las 1000 líneas.
"""
import io
import secrets

from deps import (
    api, db, get_current_user, require_roles,
    now_utc, new_id, strip_mongo_id, sanitize_user, supervisor_scope_ids,
    hash_password, normalize_role,
    LEADER_ROLES,
    UserIn, UserUpdate, SelfieIn, PinIn,
    HTTPException, Depends, UploadFile, File,
    StreamingResponse,
    Any, Dict, List, Optional,
    _load_import_lookups,
)


# ==================================================================
# USERS CRUD (5 endpoints)
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


# ------------------------------------------------------------------
# IMPORT (Excel) — DEBE registrarse ANTES de las rutas /users/{user_id}
# porque de lo contrario FastAPI intentaría casar "import" como user_id.
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# Rutas con parámetro dinámico {user_id} — DEBEN ir DESPUÉS de las
# rutas literales /users/import/* para evitar colisiones de matching.
# ------------------------------------------------------------------
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
