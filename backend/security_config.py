"""Parámetros dinámicos de seguridad y autenticación.

Guardados en la colección `settings` bajo `_id="security"`. Si el documento no
existe, se usan los valores por defecto (compatibles con la implementación
histórica hardcodeada).

Los routers deben preferir estos helpers a las constantes históricas de
`server.py`, que quedan como fallback.
"""
from __future__ import annotations
from typing import Any, Dict

# Valores por defecto — sincronizados con la versión anterior "quemada" en
# `server.py`. Cualquier campo que el admin no configure usa estos valores.
DEFAULTS: Dict[str, Any] = {
    "password_expiration_days": 90,
    "password_expiration_warning_days": 15,
    "max_login_attempts": 5,
    "lockout_minutes": 30,
    "password_history_size": 5,
    "enable_email_2fa": False,
    "otp_expiration_minutes": 5,
    "otp_max_attempts": 3,
}

# Rangos aceptados desde la UI. Se validan en el endpoint PUT.
BOUNDS: Dict[str, tuple] = {
    "password_expiration_days": (1, 365),
    "password_expiration_warning_days": (0, 60),
    "max_login_attempts": (3, 20),
    "lockout_minutes": (1, 240),
    "password_history_size": (1, 24),
    "otp_expiration_minutes": (1, 30),
    "otp_max_attempts": (1, 10),
}


async def get_security_config(db) -> Dict[str, Any]:
    """Lee la configuración vigente. Nunca falla — cae a `DEFAULTS`."""
    try:
        doc = await db.settings.find_one({"_id": "security"}) or {}
    except Exception:  # noqa: BLE001
        doc = {}
    out: Dict[str, Any] = {}
    for k, v in DEFAULTS.items():
        val = doc.get(k, v)
        if isinstance(v, bool):
            out[k] = bool(val)
        else:
            try:
                out[k] = int(val)
            except (TypeError, ValueError):
                out[k] = v
    return out


def coerce_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y normaliza el payload de PUT /security-settings.
    Devuelve el dict listo para persistir. Cualquier campo desconocido se ignora.
    """
    from fastapi import HTTPException

    updates: Dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        if key not in payload or payload[key] is None:
            continue
        raw = payload[key]
        if isinstance(default, bool):
            updates[key] = bool(raw)
            continue
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"{key}: debe ser un número entero",
            )
        lo, hi = BOUNDS[key]
        if val < lo or val > hi:
            raise HTTPException(
                status_code=400,
                detail=f"{key}: debe estar entre {lo} y {hi}",
            )
        updates[key] = val

    # Coherencia: aviso <= expiración.
    warn = updates.get("password_expiration_warning_days")
    exp = updates.get("password_expiration_days")
    if warn is not None and exp is not None and warn >= exp:
        raise HTTPException(
            status_code=400,
            detail="Los días de aviso deben ser menores que los de expiración.",
        )
    return updates
