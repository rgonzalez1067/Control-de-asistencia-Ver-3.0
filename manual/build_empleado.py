"""Genera el manual del EMPLEADO en Word (.docx).
Contenido: pantalla principal, cambio obligatorio de contraseña y registro de rostro."""
from docx import Document
from _style import (
    apply_base_style, cover, h2, h3, body, bullets, steps,
    add_image, callout,
)


def page_break(doc):
    doc.add_page_break()

IMGS = "/app/manual/imgs"
OUT = "/app/manual/manual-empleado-megasoft.docx"

doc = Document()
apply_base_style(doc)

# ================================================================
# COVER
# ================================================================
cover(
    doc,
    subtitle_top="MEGASOFT · SUITE CORPORATIVA DE ASISTENCIA",
    title="Manual del empleado",
    subtitle_bottom="Inicia sesión, cambia tu contraseña y registra tu rostro · v1.1",
)

# ================================================================
# INTRO
# ================================================================
body(doc,
    "Bienvenido/a. Este manual te guía en los pasos indispensables para dejar tu "
    "cuenta lista y poder marcar asistencia con el rostro en el kiosco de tu sede."
)
callout(doc,
    "⏱ Tiempo estimado: 3 minutos.  ·  🔒 Sólo se hace UNA vez.",
    kind="info")

# ================================================================
# 1 · PANTALLA DE INICIO
# ================================================================
h2(doc, "1", "La pantalla principal")

body(doc,
    "Cuando abres la aplicación (en el navegador o desde el ícono instalado en tu "
    "teléfono) verás la pantalla de acceso. Es la puerta de entrada al sistema.")

add_image(doc, f"{IMGS}/01-login.jpeg",
          "Pantalla principal · Acceso a MegaSoft Asistencia")

h3(doc, "Cómo iniciar sesión")
steps(doc, [
    "Escribe tu correo corporativo en el campo “Correo”.",
    "Escribe la contraseña que te entregó Recursos Humanos.",
    "Si dudas de haber tecleado bien, toca el ojito 👁 para ver la contraseña.",
    "Pulsa el botón azul “Iniciar sesión”.",
])

add_image(doc, f"{IMGS}/02-login-fill.jpeg",
          "Ejemplo con credenciales completadas")

callout(doc,
    "💡 Si olvidaste tu contraseña avisa a tu supervisor o a RRHH — ellos pueden "
    "reasignártela en segundos.",
    kind="tip")

# ================================================================
# 2 · CAMBIO OBLIGATORIO DE CONTRASEÑA
# ================================================================
page_break(doc)
h2(doc, "2", "Cambio obligatorio de contraseña (primer ingreso)")

body(doc,
    "La primera vez que entras — o después de que RRHH restablezca tu contraseña — "
    "el sistema NO te dejará usar el resto de la aplicación hasta que definas una "
    "contraseña personal y segura.")

add_image(doc, f"{IMGS}/04-changepw-empty.jpeg",
          "Pantalla de cambio obligatorio de contraseña · estado inicial")

h3(doc, "Reglas de la contraseña")
bullets(doc, [
    "Mínimo 8 caracteres.",
    "Al menos 1 letra mayúscula (A–Z).",
    "Al menos 1 letra minúscula (a–z).",
    "Al menos 1 número (0–9).",
    "Al menos 1 símbolo (por ejemplo: * # ! $ @).",
    "No puede ser igual a la contraseña temporal ni contener tu correo.",
])

h3(doc, "Cómo cambiarla")
steps(doc, [
    "Escribe la contraseña actual (la temporal que te dieron).",
    "Escribe tu nueva contraseña — a la derecha del campo hay un ojito 👁 que te deja ver lo que escribes. Debajo, los requisitos se marcan en verde a medida que los cumples.",
    "Repítela en “Confirmar contraseña”. El botón “Cambiar contraseña” sólo se activa cuando todo está correcto.",
    "Pulsa “Cambiar contraseña”. El sistema te llevará automáticamente al menú principal.",
])

add_image(doc, f"{IMGS}/04-changepw-filled.jpeg",
          "Ejemplo con la nueva contraseña ya escrita · todos los requisitos en verde")

callout(doc,
    "🔒 Nadie de la empresa — ni RRHH, ni sistemas — puede ver tu nueva contraseña. "
    "Sólo tú la conoces. Anótala en un lugar seguro.",
    kind="note")

callout(doc,
    "⚠️ Si te equivocas tres veces al escribir la actual, deberás pedir un nuevo "
    "restablecimiento a RRHH.",
    kind="warn")

# ================================================================
# 3 · REGISTRO DE ROSTRO
# ================================================================
page_break(doc)
h2(doc, "3", "Registro de tu foto para el kiosco")

body(doc,
    "El kiosco de asistencia reconoce tu cara para marcar la entrada y la salida "
    "de forma instantánea, sin PIN, sin tocar la pantalla. Para que funcione, "
    "necesitamos registrar una foto tuya (una sola vez).")

body(doc, "Puedes hacerlo desde cualquier computador o teléfono con cámara.")

h3(doc, "Abrir el asistente")
steps(doc, [
    "Ya con la sesión iniciada, pulsa tu inicial/foto arriba a la derecha.",
    "Selecciona “Registrar mi rostro”.",
])

add_image(doc, f"{IMGS}/03-usermenu.jpeg",
          "Menú de usuario · opción “Registrar mi rostro”")

h3(doc, "Tomar la selfie")
steps(doc, [
    "Autoriza el permiso de cámara cuando el navegador te lo pida.",
    "Ubícate en un lugar bien iluminado, mirando de frente a la cámara.",
    "Encaja tu cara dentro del círculo guía. El sistema te avisa cuando la detección es buena.",
    "Pulsa “Capturar”. Revisa la vista previa — si te gusta, pulsa “Guardar”.",
    "Listo. Verás una etiqueta “✓ Rostro registrado” en tu perfil.",
])

add_image(doc, f"{IMGS}/05-onboarding.jpeg",
          "Asistente de captura de rostro")

h3(doc, "Consejos para una buena captura")
bullets(doc, [
    "Buena luz frontal — evita luces detrás de ti (contraluz).",
    "Retira lentes oscuros y gorra con visera.",
    "Rostro neutral, sin sonrisa exagerada. Boca cerrada.",
    "Sin filtros ni fotos de fotos. La captura debe ser en vivo con la cámara.",
    "Si usas lentes correctivos, regístrate CON ellos puestos — el kiosco los aceptará.",
])

callout(doc,
    "🔁 Si tu apariencia cambia mucho (corte de cabello radical, barba, etc.) puedes "
    "volver a tomarte la foto en cualquier momento desde el mismo menú. El sistema "
    "reemplazará la anterior.",
    kind="tip")

# ================================================================
# 4 · YA ESTÁS LISTO/A
# ================================================================
page_break(doc)
h2(doc, "4", "Ya estás listo/a")

body(doc,
    "Con contraseña personal y rostro registrado, ya puedes acercarte al kiosco "
    "de tu sede y marcar entrada/salida en menos de 2 segundos. Buen día. 🚀")

bullets(doc, [
    "Recuerda: el kiosco marca automáticamente entrada o salida según sea tu primer o segundo paso.",
    "Si el kiosco no reconoce tu cara, puedes usar tu cédula + PIN como respaldo.",
    "Tu supervisor o RRHH pueden ayudarte si algo no funciona.",
])

# ================================================================
# SAVE
# ================================================================
doc.save(OUT)
print(f"OK · {OUT}")
