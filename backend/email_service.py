"""Servicio de correo transaccional vía SMTP corporativo.

Lee credenciales de `.env`. Si SMTP_HOST no está definido, `send_email()`
opera en modo NO-OP y devuelve `{'sent': False, 'reason': 'smtp_not_configured'}`
— así el flujo de reset no se rompe en entornos sin correo (p.ej. preview).

Variables de entorno esperadas (definir en backend/.env):
    SMTP_HOST=mail.megasoft.com.ve
    SMTP_PORT=587
    SMTP_USER=no-reply@megasoft.com.ve
    SMTP_PASSWORD=***
    SMTP_FROM="Megasoft Asistencia <no-reply@megasoft.com.ve>"
    SMTP_TLS=starttls   # starttls | ssl | plain
    APP_PUBLIC_URL=https://asistencia-web-1.preview.emergentagent.com
"""
from __future__ import annotations
import os
import logging
from email.message import EmailMessage
from typing import Optional, Dict, Any

import aiosmtplib

logger = logging.getLogger("megasoft.email")


def _cfg() -> Dict[str, Any]:
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT") or 0),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "from_addr": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER"),
        "tls_mode": (os.environ.get("SMTP_TLS") or "starttls").lower(),
    }


def is_configured() -> bool:
    c = _cfg()
    return bool(c["host"] and c["port"] and c["from_addr"])


async def send_email(to: str, subject: str, text_body: str,
                     html_body: Optional[str] = None) -> Dict[str, Any]:
    """Envía un correo. Devuelve {sent, reason?}. Nunca lanza — errores se loggean."""
    if not is_configured():
        logger.warning("SMTP no configurado. Se omite envío a %s: %s", to, subject)
        return {"sent": False, "reason": "smtp_not_configured"}
    c = _cfg()
    msg = EmailMessage()
    msg["From"] = c["from_addr"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    tls_mode = c["tls_mode"]
    try:
        await aiosmtplib.send(
            msg,
            hostname=c["host"],
            port=c["port"],
            username=c["user"] or None,
            password=c["password"] or None,
            use_tls=(tls_mode == "ssl"),
            start_tls=(tls_mode == "starttls"),
            timeout=15,
        )
        logger.info("Email enviado a %s (asunto=%s)", to, subject)
        return {"sent": True}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error enviando email a %s: %s", to, exc)
        return {"sent": False, "reason": str(exc)[:200]}


def render_reset_email(name: str, link: str, minutes_valid: int = 30) -> Dict[str, str]:
    text = (
        f"Hola {name},\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta en Megasoft Asistencia.\n\n"
        f"Ingresa al siguiente enlace (válido por {minutes_valid} minutos) para elegir una nueva:\n"
        f"{link}\n\n"
        "Si no solicitaste este cambio, ignora este mensaje — tu contraseña no cambiará.\n\n"
        "— Megasoft Asistencia"
    )
    html = f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f6f7fb;padding:24px">
<table cellpadding="0" cellspacing="0" style="max-width:520px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
  <tr><td style="padding:20px 24px;background:#0f172a;color:#fff;font-size:16px;font-weight:600">Megasoft Asistencia</td></tr>
  <tr><td style="padding:24px">
    <p style="margin:0 0 12px;color:#0f172a">Hola {name},</p>
    <p style="margin:0 0 12px;color:#475569">Recibimos una solicitud para restablecer tu contraseña.</p>
    <p style="margin:16px 0"><a href="{link}" style="display:inline-block;padding:12px 20px;background:#f59e0b;color:#111827;font-weight:600;border-radius:999px;text-decoration:none">Restablecer contraseña</a></p>
    <p style="margin:0 0 8px;color:#64748b;font-size:12px">El enlace es válido por <b>{minutes_valid} minutos</b>. Si no lo solicitaste, ignora este mensaje.</p>
    <p style="margin:12px 0 0;color:#94a3b8;font-size:11px">O copia y pega este enlace en tu navegador:<br><span style="word-break:break-all">{link}</span></p>
  </td></tr>
</table></body></html>"""
    return {"text": text, "html": html}
