"""Genera el Manual del Empleado (Word .docx) con capturas del app.

Uso:
    python3 /app/manual/build_manual.py
Produce:
    /app/manual/Manual_Empleado_MegaSoft_Asistencia.docx
"""
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SCREENS = "/app/manual/screens"
OUT = "/app/manual/Manual_Empleado_MegaSoft_Asistencia.docx"

NAVY = RGBColor(0x0B, 0x1F, 0x3A)
AMBER = RGBColor(0xC7, 0x8A, 0x1F)
RED = RGBColor(0xB0, 0x2A, 0x2A)
EMERALD = RGBColor(0x1F, 0x7A, 0x4C)
GREY = RGBColor(0x55, 0x5D, 0x6A)


def _shade_cell(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _run(paragraph, text, bold=False, size=None, color=None, italic=False):
    r = paragraph.add_run(text)
    r.bold = bold
    r.italic = italic
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    r.font.name = "Calibri"
    return r


def add_heading(doc, text, level=1, color=None):
    h = doc.add_heading("", level=level)
    r = h.add_run(text)
    r.font.name = "Calibri"
    if color:
        r.font.color.rgb = color
    return h


def add_para(doc, text=None, bold=False, size=11, color=None, italic=False, align=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    if text is not None:
        _run(p, text, bold=bold, size=size, color=color, italic=italic)
    return p


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Cm(0.5 + level * 0.6)
    _run(p, text, size=11)
    return p


def add_num(doc, text):
    p = doc.add_paragraph(style="List Number")
    _run(p, text, size=11)
    return p


def add_image(doc, path, width_cm=15.5, caption=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(cap, f"Figura: {caption}", size=9, italic=True, color=GREY)


def add_callout(doc, title, body, color_hex="FFF6E5", accent=AMBER):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.autofit = True
    cell = tbl.rows[0].cells[0]
    _shade_cell(cell, color_hex)
    p1 = cell.paragraphs[0]
    _run(p1, "► " + title, bold=True, size=11, color=accent)
    for line in body:
        p = cell.add_paragraph()
        _run(p, line, size=10.5)


def add_page_break(doc):
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


# ------------------- BUILD DOCUMENT -------------------
doc = Document()

# Márgenes
for sec in doc.sections:
    sec.top_margin = Cm(2.0)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(2.2)
    sec.right_margin = Cm(2.2)

# Portada
cover = doc.add_paragraph()
cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
_run(cover, "MegaSoft Computación, C.A.\n", bold=True, size=14, color=NAVY)
_run(cover, "Suite Corporativa de Asistencia\n\n\n", size=12, color=GREY)

_run(cover, "\n\nMANUAL DEL EMPLEADO\n\n", bold=True, size=28, color=NAVY)
_run(cover, "Uso del sistema web / PWA\n", size=14, color=AMBER, italic=True)
_run(cover, "Marcaje, historial, justificaciones y novedades\n", size=12, color=GREY)

_run(cover, "\n\n\n\n\n\n\n\n\n\nVersión 1.0 — Febrero 2026\n", size=11, color=GREY)
_run(cover, "Dirigido a: Personal operativo (rol Empleado)\n", size=11, color=GREY)
add_page_break(doc)

# ---------------- ÍNDICE ----------------
add_heading(doc, "Contenido", level=1, color=NAVY)
toc = [
    "1.  Introducción",
    "2.  Cómo iniciar sesión",
    "3.  Recorrido de la pantalla principal",
    "4.  Menú de tu cuenta (foto, contraseña y PIN)",
    "5.  Mi historial — Consulta de tus marcajes",
    "     5.1  Interpretación de estados y colores",
    "     5.2  E1 y E2+ — Cálculo del retraso",
    "     5.3  Cómo justificar una tardanza (paso a paso)",
    "     5.4  Estado de tu justificación: pendiente / aceptada / rechazada",
    "6.  Novedades — Vacaciones, reposos y permisos",
    "     6.1  Tipos de novedad aceptados",
    "     6.2  Cómo solicitar una novedad (paso a paso)",
    "     6.3  Ciclo de aprobación y qué esperar",
    "7.  Mi carnet — Credencial digital y PIN de contingencia",
    "8.  Agendar visitas de terceros",
    "9.  Marcaje en el kiosco (contexto)",
    "10. Preguntas frecuentes y buenas prácticas",
    "11. Contacto y soporte",
]
for t in toc:
    p = doc.add_paragraph()
    _run(p, t, size=11)
add_page_break(doc)

# ---------------- 1. INTRODUCCIÓN ----------------
add_heading(doc, "1. Introducción", level=1, color=NAVY)
add_para(doc,
    "Bienvenido/a a la Suite Corporativa de Asistencia de MegaSoft. Esta aplicación web "
    "reemplaza al app móvil anterior y funciona directamente desde tu navegador o instalada "
    "como PWA en tu equipo o teléfono. Este manual está orientado exclusivamente al perfil "
    "Empleado y describe con detalle cada opción a la que tienes acceso.",
    size=11)
add_para(doc,
    "Como empleado podrás:", size=11)
add_bullet(doc, "Consultar tus marcajes diarios y del mes (Mi Historial).")
add_bullet(doc, "Justificar tardanzas cuando llegues fuera de la hora asignada.")
add_bullet(doc, "Registrar novedades laborales (vacaciones, reposos médicos, permisos, etc.).")
add_bullet(doc, "Ver tu credencial digital (Mi Carnet).")
add_bullet(doc, "Agendar visitas de terceros a tu sede.")
add_bullet(doc, "Cambiar tu contraseña y tu PIN personal.")
add_callout(doc, "IMPORTANTE",
    ["El registro de entrada y salida (marcaje) se realiza únicamente desde el kiosco físico con reconocimiento facial. Desde esta aplicación web NO se marca entrada/salida.",
     "Este sistema web es tu portal de consulta, justificación y gestión de novedades."],
    color_hex="FFF6E5", accent=AMBER)
add_page_break(doc)

# ---------------- 2. LOGIN ----------------
add_heading(doc, "2. Cómo iniciar sesión", level=1, color=NAVY)
add_num(doc, "Abre tu navegador (Chrome, Edge, Firefox o Safari recomendados) e ingresa a la URL corporativa que te suministró tu supervisor.")
add_num(doc, "Ingresa tu correo institucional en el campo 'Correo electrónico'.")
add_num(doc, "Ingresa la contraseña que te fue asignada.")
add_num(doc, "Presiona el botón azul 'Entrar al panel'.")
add_image(doc, f"{SCREENS}/01_login.jpg", width_cm=15.5, caption="Pantalla de inicio de sesión.")
add_callout(doc, "SI TIENES PROBLEMAS PARA ENTRAR",
    ["Verifica que estás usando tu correo corporativo (ejemplo: nombre@megasoft.com.ve).",
     "Si olvidaste tu contraseña o nunca has ingresado, contacta a Recursos Humanos.",
     "El vínculo 'zona segura · JWT · TLS' te confirma que la conexión está cifrada."],
    color_hex="EEF5FF", accent=NAVY)
add_page_break(doc)

# ---------------- 3. PANTALLA PRINCIPAL ----------------
add_heading(doc, "3. Recorrido de la pantalla principal", level=1, color=NAVY)
add_para(doc,
    "Al entrar por primera vez el sistema te llevará directamente a Mi Historial. Este es "
    "tu punto de partida diario y el lugar donde verás toda tu actividad de marcajes.",
    size=11)
add_image(doc, f"{SCREENS}/02_dashboard.jpg", width_cm=15.5, caption="Pantalla principal del empleado (redirige a Mi Historial).")

add_heading(doc, "Elementos que ves en pantalla:", level=2)
add_bullet(doc, "Barra lateral izquierda (menú): Mi carnet · Historial · Agendar visita · Histórico de visitas. Si tu perfil de acceso incluye novedades, verás también la opción 'Novedades'.")
add_bullet(doc, "Barra superior: saludo con tu nombre + iconos de modo claro/oscuro y menú de tu cuenta (iniciales sobre círculo azul).")
add_bullet(doc, "Área central: contenido de la sección donde te encuentras.")
add_bullet(doc, "Pie de página: versión de la aplicación y ambiente (Producción / Preview).")

add_page_break(doc)

# ---------------- 4. MENÚ USUARIO ----------------
add_heading(doc, "4. Menú de tu cuenta (foto, contraseña y PIN)", level=1, color=NAVY)
add_para(doc, "Haz clic en tu avatar (iniciales en la esquina superior derecha) para desplegar las opciones personales:", size=11)
add_image(doc, f"{SCREENS}/10_menu_usuario.jpg", width_cm=15.5, caption="Menú desplegable de la cuenta del empleado.")
add_bullet(doc, "Registrar rostro: te permite re-tomar tu selfie de referencia si el kiosco tiene dificultades para reconocerte.")
add_bullet(doc, "Cambiar contraseña: cambia tu clave de acceso a esta app.")
add_bullet(doc, "Cambiar PIN: modifica tu PIN de 4 a 8 dígitos utilizado en el kiosco cuando la cámara no puede reconocerte.")
add_bullet(doc, "Cerrar sesión: sale del sistema.")

add_heading(doc, "4.1 Cambiar contraseña", level=2)
add_num(doc, "Selecciona 'Cambiar contraseña' del menú.")
add_num(doc, "Ingresa tu contraseña actual.")
add_num(doc, "Ingresa la nueva contraseña (mínimo 8 caracteres, debe ser distinta a la actual). Se recomiendan mayúsculas, números y símbolos.")
add_num(doc, "Confirma la nueva contraseña y presiona 'Actualizar'.")
add_image(doc, f"{SCREENS}/12_cambiar_password.jpg", width_cm=13.5, caption="Diálogo para cambiar la contraseña de la aplicación.")

add_heading(doc, "4.2 Cambiar PIN", level=2)
add_num(doc, "Selecciona 'Cambiar PIN' del menú.")
add_num(doc, "Ingresa tu contraseña actual (para confirmar identidad).")
add_num(doc, "Escribe el nuevo PIN (entre 4 y 8 dígitos).")
add_num(doc, "Repite el PIN en 'Confirmar PIN' y presiona 'Guardar PIN'.")
add_image(doc, f"{SCREENS}/13_cambiar_pin.jpg", width_cm=13.5, caption="Diálogo para cambiar el PIN de marcaje del kiosco.")

add_callout(doc, "¿PARA QUÉ SIRVE EL PIN?",
    ["El PIN es un código numérico personal (privado) que usarás únicamente en el kiosco físico cuando el reconocimiento facial falle (por ejemplo, iluminación deficiente o lentes de sol).",
     "Nunca lo compartas ni lo escribas en lugares visibles.",
     "Si sospechas que otra persona lo conoce, cámbialo inmediatamente desde este menú."],
    color_hex="EEF5FF", accent=NAVY)

add_page_break(doc)

# ---------------- 5. MI HISTORIAL ----------------
add_heading(doc, "5. Mi historial — Consulta de tus marcajes", level=1, color=NAVY)
add_para(doc,
    "Esta pantalla concentra todas las marcas de entrada y salida que has realizado desde "
    "el kiosco con reconocimiento facial. Además te permite justificar tardanzas y ver el "
    "resultado (aprobación o rechazo) de las justificaciones que hayas enviado.",
    size=11)
add_image(doc, f"{SCREENS}/03_historial.jpg", width_cm=16.5, caption="Mi Historial: KPIs superiores y tabla de marcajes.")

add_heading(doc, "Elementos de la pantalla:", level=2)
add_bullet(doc, "KPIs superiores: Entradas hoy · Salidas hoy · Entradas del mes · Tardanzas del mes (en color ámbar cuando hay alguna).")
add_bullet(doc, "Tabla de marcajes: cada fila es una marca con Fecha, Hora, Tipo (Entrada / Salida), Sede, Estado y Justificación.")

# --------- 5.1 Estados y colores ---------
add_heading(doc, "5.1 Interpretación de estados y colores", level=2)

# Tabla de estados
tbl = doc.add_table(rows=6, cols=3)
tbl.style = "Light Grid Accent 1"
hdr = tbl.rows[0].cells
_run(hdr[0].paragraphs[0], "Estado", bold=True, size=10, color=NAVY)
_run(hdr[1].paragraphs[0], "Cómo se ve", bold=True, size=10, color=NAVY)
_run(hdr[2].paragraphs[0], "Qué significa", bold=True, size=10, color=NAVY)
rows = [
    ("A tiempo", "Verde", "Marcaste dentro del horario o dentro de la tolerancia general (10 min)."),
    ("Retraso leve", "Ámbar", "Marcaste después de la tolerancia general pero dentro de la ventana de justificación. Podría requerir justificación."),
    ("Retraso mayor", "Rojo · con ícono ⚠", "Excede la ventana de justificación. Es obligatorio justificar. El signo '!' indica que aún no lo has hecho."),
    ("Exceso de descanso", "Rojo (hora en rojo)", "Aplica sólo a la Segunda Entrada del día (E2). Excediste 60 minutos entre S1 y E2. Ver sección 5.2."),
    ("Pendiente de aprobación", "Ámbar (badge)", "Ya enviaste tu justificación; tu supervisor aún no la ha aceptado ni rechazado."),
]
for i, (a, b, c) in enumerate(rows, start=1):
    tbl.rows[i].cells[0].paragraphs[0].add_run(a).font.size = Pt(10)
    tbl.rows[i].cells[1].paragraphs[0].add_run(b).font.size = Pt(10)
    tbl.rows[i].cells[2].paragraphs[0].add_run(c).font.size = Pt(10)

# 5.2 E1/E2
add_heading(doc, "5.2 E1 y E2+ — Cálculo del retraso", level=2)
add_para(doc,
    "El sistema distingue dos situaciones distintas cuando marcas 'Entrada':", size=11)

add_para(doc, "Entrada 1 (E1) — La primera del día:", bold=True, size=11, color=NAVY)
add_bullet(doc, "Se compara con la hora de inicio de tu horario más la tolerancia general.")
add_bullet(doc, "Ejemplo: si tu horario inicia 08:00 y la tolerancia general es 10 minutos, marcar hasta las 08:10 → 'A tiempo'. Después → 'Retraso leve' o 'mayor' según la ventana de justificación.")

add_para(doc, "Entrada 2 en adelante (E2, E3, …) — Tras un descanso:", bold=True, size=11, color=NAVY)
add_bullet(doc, "Cuando ya marcaste una entrada (E1) y una salida (S1) y vuelves a marcar entrada, el sistema considera que estás regresando de descanso.")
add_bullet(doc, "El cálculo ya NO se hace contra la hora del horario. Se hace midiendo el tiempo transcurrido entre S1 (tu primera salida) y E2 (tu segunda entrada).")

# Tabla resumen E2
tbl2 = doc.add_table(rows=3, cols=4)
tbl2.style = "Light Grid Accent 1"
h2 = tbl2.rows[0].cells
_run(h2[0].paragraphs[0], "Intervalo (S1 → E2)", bold=True, size=10, color=NAVY)
_run(h2[1].paragraphs[0], "Color del marcaje", bold=True, size=10, color=NAVY)
_run(h2[2].paragraphs[0], "Minutos de retraso", bold=True, size=10, color=NAVY)
_run(h2[3].paragraphs[0], "¿Requiere justificar?", bold=True, size=10, color=NAVY)

r2 = tbl2.rows[1].cells
_run(r2[0].paragraphs[0], "≤ 60 minutos", size=10)
_run(r2[1].paragraphs[0], "Negro (normal)", size=10)
_run(r2[2].paragraphs[0], "0 min", size=10)
_run(r2[3].paragraphs[0], "No", size=10)

r3 = tbl2.rows[2].cells
_run(r3[0].paragraphs[0], "> 60 minutos", size=10)
_run(r3[1].paragraphs[0], "Rojo (llamativo)", size=10, color=RED, bold=True)
_run(r3[2].paragraphs[0], "(Tiempo total − 60) min", size=10)
_run(r3[3].paragraphs[0], "Sí (obligatorio)", size=10, bold=True)

add_callout(doc, "EJEMPLO PRÁCTICO",
    ["Marcaste S1 a las 12:00 y regresas E2 a las 13:15. Δt = 75 min > 60 → tu retraso será de 15 minutos y verás la hora 01:15 p.m. en color rojo. El sistema te pedirá justificar.",
     "Si en cambio E2 fuese a las 12:45, Δt = 45 min ≤ 60 → NO habría retraso, la hora aparecería en negro y no se te pediría justificación."],
    color_hex="FDECEC", accent=RED)

# 5.3 Justificar paso a paso
add_heading(doc, "5.3 Cómo justificar una tardanza (paso a paso)", level=2)
add_para(doc,
    "Cuando en la columna 'Justificación' aparezca el botón 'Justificar' (icono de globo), tienes derecho a explicar el motivo de tu tardanza. Sigue estos pasos:",
    size=11)
add_num(doc, "En la fila de la tardanza que quieres justificar, presiona el botón 'Justificar' que aparece en la columna Justificación.")
add_num(doc, "Se abrirá un diálogo titulado 'Justificar tardanza' donde debes escribir un texto claro (mínimo 5 caracteres) explicando qué ocurrió.")
add_num(doc, "Sé específico: menciona lugar, motivo y, de ser posible, ofrece la posibilidad de compartir evidencia a tu supervisor (ej. captura de Waze, informe de tráfico).")
add_num(doc, "Presiona el botón 'Enviar justificación'.")
add_image(doc, f"{SCREENS}/04_historial_justificar.jpg", width_cm=14.5, caption="Diálogo para enviar la justificación al supervisor.")

add_callout(doc, "BUENAS PRÁCTICAS AL JUSTIFICAR",
    ["Justifica el mismo día o al día siguiente. Justificaciones muy tardías pueden ser rechazadas.",
     "Escribe en primera persona y con un tono profesional. Ej.: 'Retraso ocasionado por congestión vial en la Autopista Regional del Centro debido a un accidente vehicular a la altura de Guacara. Adjunto captura de Waze al supervisor.'",
     "Evita frases genéricas como 'tráfico' o 'lluvia' sin contexto: le dan pocas herramientas al supervisor para decidir.",
     "Si es un caso recurrente, coordina con tu supervisor un cambio de horario o vía alternativa."],
    color_hex="FFF6E5", accent=AMBER)

# 5.4 Estados posteriores
add_heading(doc, "5.4 Estado de tu justificación: pendiente / aceptada / rechazada", level=2)
add_para(doc,
    "Después de enviar tu justificación, el registro cambia de estado. Puedes verificarlo en la misma tabla de Mi Historial:",
    size=11)
add_bullet(doc, "Pendiente de aprobación (badge ámbar): tu supervisor aún no la ha revisado.")
add_bullet(doc, "Justificado (badge verde): tu supervisor la aceptó. La tardanza NO computa en tus reportes de minutos perdidos.")
add_bullet(doc, "Injustificado (badge rojo con 'Motivo: …'): tu supervisor la rechazó. Podrás leer la razón que registró. Los minutos SÍ se suman a los reportes.")

add_callout(doc, "¿QUÉ HACER SI FUE RECHAZADA?",
    ["Lee con atención la razón registrada por el supervisor.",
     "Si consideras que hay información adicional relevante, comunícate en persona o por correo con tu supervisor. La justificación en el sistema no se puede editar una vez decidida.",
     "Si aportas pruebas nuevas, tu supervisor puede solicitar a Recursos Humanos que anule la penalización manualmente."],
    color_hex="EEF5FF", accent=NAVY)

add_page_break(doc)

# ---------------- 6. NOVEDADES ----------------
add_heading(doc, "6. Novedades — Vacaciones, reposos y permisos", level=1, color=NAVY)
add_para(doc,
    "Una NOVEDAD es cualquier ausencia planificada o eventual que quieras que quede registrada "
    "oficialmente ante tu supervisor y Recursos Humanos. Ejemplos: vacaciones, permisos médicos, "
    "trámites personales, visita a cliente, teletrabajo, entre otros.",
    size=11)
add_para(doc,
    "Si tu perfil de acceso incluye 'Novedades', verás la opción en el menú lateral. Si no la tienes, "
    "solicítala a Recursos Humanos.",
    size=10, italic=True, color=GREY)

# 6.1 Tipos
add_heading(doc, "6.1 Tipos de novedad aceptados", level=2)
tbl3 = doc.add_table(rows=8, cols=2)
tbl3.style = "Light Grid Accent 1"
h3 = tbl3.rows[0].cells
_run(h3[0].paragraphs[0], "Tipo", bold=True, size=10, color=NAVY)
_run(h3[1].paragraphs[0], "Uso típico", bold=True, size=10, color=NAVY)
tipos = [
    ("Vacaciones", "Días de vacaciones legales (día completo, sin hora)."),
    ("Permiso", "Trámites personales, cita médica corta, gestiones familiares (con hora de inicio y fin)."),
    ("Reposo médico", "Cuando presentas incapacidad emitida por un médico. Recuerda entregar el original a RRHH."),
    ("Licencia (leave)", "Licencias especiales (maternidad, paternidad, luto)."),
    ("Remoto / Teletrabajo", "Días en que trabajarás desde casa por acuerdo previo."),
    ("Visita a cliente", "Cuando estarás fuera de la sede en visita técnica o comercial."),
    ("Otro", "Situaciones que no encajen en las anteriores. Explica bien el motivo."),
]
for i, (t, u) in enumerate(tipos, start=1):
    tbl3.rows[i].cells[0].paragraphs[0].add_run(t).font.size = Pt(10)
    tbl3.rows[i].cells[1].paragraphs[0].add_run(u).font.size = Pt(10)

add_image(doc, f"{SCREENS}/05_novedades_list.jpg", width_cm=16.5, caption="Pantalla 'Novedades' con las pestañas Pendientes, Historial y Todas.")

# 6.2 Solicitar novedad
add_heading(doc, "6.2 Cómo solicitar una novedad (paso a paso)", level=2)
add_num(doc, "Selecciona 'Novedades' en el menú lateral.")
add_num(doc, "Presiona el botón azul '+ Nueva novedad' en la parte superior derecha.")
add_num(doc, "En 'Tipo' selecciona la naturaleza de la novedad (Vacaciones, Permiso, Reposo, etc.).")
add_num(doc, "En 'Desde' y 'Hasta' selecciona las fechas de inicio y fin. Para novedades de un solo día, coloca la misma fecha en ambos campos.")
add_num(doc, "Cuando la novedad NO sea de día completo, indica también 'Hora inicio' y 'Hora fin'. Vacaciones no requiere horas.")
add_num(doc, "En 'Motivo' escribe una explicación breve (opcional pero recomendado para agilizar la aprobación).")
add_num(doc, "Presiona 'Enviar solicitud'. La novedad quedará en estado Pendiente hasta que tu supervisor la revise.")
add_image(doc, f"{SCREENS}/06_novedades_form.jpg", width_cm=13.5, caption="Formulario para crear una nueva novedad.")

# 6.3 Ciclo
add_heading(doc, "6.3 Ciclo de aprobación y qué esperar", level=2)
add_bullet(doc, "Pendiente: tu supervisor recibió la solicitud y aún no ha decidido.")
add_bullet(doc, "Aprobada: la novedad queda oficial y se refleja en la matriz de asistencia. Los días cubiertos NO cuentan como faltas.")
add_bullet(doc, "Rechazada: tu supervisor consideró que la solicitud no procede. Puedes ver el motivo del rechazo. En ese caso, deberás cumplir con tu horario habitual esos días.")

add_callout(doc, "RECOMENDACIONES CLAVE PARA NOVEDADES",
    ["Anticipa: solicita vacaciones y permisos con la mayor antelación posible.",
     "Reposos médicos: entrega el original firmado y sellado a Recursos Humanos, además de registrarlo en el sistema.",
     "Un mismo período no puede tener dos novedades activas. Si detectas un error, cancela y crea la novedad correcta.",
     "Si la novedad tapa un día en el que ya marcaste asistencia, el sistema conserva el marcaje. La novedad no borra tus marcas."],
    color_hex="FFF6E5", accent=AMBER)

add_page_break(doc)

# ---------------- 7. MI CARNET ----------------
add_heading(doc, "7. Mi carnet — Credencial digital y PIN de contingencia", level=1, color=NAVY)
add_para(doc,
    "En 'Mi carnet' encontrarás tu credencial digital corporativa con tu foto de referencia, "
    "tu identificación y tu QR de contingencia. Puedes descargarla o mostrarla en pantalla "
    "cuando lo necesites.",
    size=11)
add_image(doc, f"{SCREENS}/07_carnet.jpg", width_cm=16.5, caption="Vista de Mi Carnet.")
add_bullet(doc, "Verifica que los datos personales sean correctos.")
add_bullet(doc, "Si tu foto está borrosa o desactualizada, ve al menú de tu cuenta > 'Registrar rostro'.")

add_page_break(doc)

# ---------------- 8. VISITAS ----------------
add_heading(doc, "8. Agendar visitas de terceros", level=1, color=NAVY)
add_para(doc,
    "Si un cliente, proveedor o familiar viene a tu sede, puedes agendarlo de forma anticipada "
    "para que el personal de recepción/vigilancia lo esté esperando y agilizar el ingreso.",
    size=11)
add_num(doc, "Selecciona 'Agendar visita' en el menú lateral.")
add_num(doc, "Completa los datos del visitante: nombre, cédula, empresa (si aplica) y motivo.")
add_num(doc, "Indica fecha y hora estimada de llegada.")
add_num(doc, "Envía el formulario. Recibirás confirmación en pantalla y podrás verlo en 'Histórico de visitas'.")
add_image(doc, f"{SCREENS}/08_visitas_agendar.jpg", width_cm=16.5, caption="Formulario para agendar una visita.")
add_para(doc, "Consulta el estado de tus visitas anteriores en 'Histórico de visitas':", size=11)
add_image(doc, f"{SCREENS}/09_visitas_historico.jpg", width_cm=16.5, caption="Histórico de visitas. Nota: si aparece 'No tienes permiso', tu perfil no tiene habilitada esa opción; solicítala a tu supervisor.")

add_page_break(doc)

# ---------------- 9. KIOSCO ----------------
add_heading(doc, "9. Marcaje en el kiosco (contexto)", level=1, color=NAVY)
add_para(doc,
    "Los marcajes de Entrada y Salida se realizan ÚNICAMENTE en el kiosco físico ubicado en tu sede. "
    "El kiosco reconoce tu rostro y registra automáticamente la hora exacta. No es posible marcar "
    "desde esta aplicación web.",
    size=11)
add_para(doc, "Recordatorios importantes al usar el kiosco:", bold=True, size=11)
add_bullet(doc, "Colócate frente a la cámara con el rostro descubierto (no uses gorra, capucha o lentes muy oscuros).")
add_bullet(doc, "Espera 1-2 segundos hasta que aparezca la confirmación 'Sí, soy yo' o 'No soy yo'.")
add_bullet(doc, "Si el kiosco no logra reconocerte, presiona 'Ingresar por PIN' e introduce el PIN personal que definiste en la sección 4.2.")
add_bullet(doc, "Nunca marques por otra persona. Es una falta grave y queda registrada.")

add_callout(doc, "¿QUÉ HACER SI EL KIOSCO ESTÁ FUERA DE LÍNEA?",
    ["Informa de inmediato al personal de RRHH o al supervisor de sede.",
     "Los marcajes que no logres realizar se corregirán manualmente contra tu justificación y las cámaras de seguridad.",
     "No intentes 'compensar' marcando fuera del kiosco desde otro equipo: no está permitido."],
    color_hex="EEF5FF", accent=NAVY)

add_page_break(doc)

# ---------------- 10. FAQ ----------------
add_heading(doc, "10. Preguntas frecuentes y buenas prácticas", level=1, color=NAVY)

faq = [
    ("¿Puedo marcar entrada o salida desde esta web?",
     "No. El marcaje se realiza exclusivamente en el kiosco de tu sede con reconocimiento facial. Este portal es de consulta y gestión."),
    ("Marqué tarde y no aparece el botón 'Justificar'. ¿Por qué?",
     "El botón aparece únicamente en filas con is_late=Sí. Si la tardanza está clasificada como 'Retraso leve' dentro de la tolerancia, no se te exige justificar (aunque puedes hacerlo si tu supervisor lo pide)."),
    ("Envié una justificación y no cambia el estado.",
     "El supervisor debe entrar al sistema y aprobar/rechazar. Contáctalo si han pasado más de 48 horas hábiles sin decisión."),
    ("¿Puedo cancelar una novedad ya enviada?",
     "Sí, mientras esté en estado Pendiente. Una vez aprobada, deberás pedir a tu supervisor que la anule."),
    ("Perdí mi PIN o lo olvidé.",
     "Cámbialo desde el menú de tu cuenta > 'Cambiar PIN' (necesitarás tu contraseña actual). Si tampoco recuerdas la contraseña, contacta a RRHH."),
    ("Me equivoqué al marcar (marqué salida en vez de entrada).",
     "El sistema registra ambos tipos sin sobreponerlos. Vuelve al kiosco y marca el tipo correcto. Si notas una anomalía, avisa a tu supervisor."),
    ("Puedo instalar la app en mi teléfono?",
     "Sí. Abre la URL en Chrome/Safari y elige 'Instalar app' o 'Añadir a pantalla de inicio'. Funcionará como PWA con icono propio."),
]
for q, a in faq:
    add_para(doc, "P: " + q, bold=True, size=11, color=NAVY)
    add_para(doc, "R: " + a, size=11)

add_page_break(doc)

# ---------------- 11. CONTACTO ----------------
add_heading(doc, "11. Contacto y soporte", level=1, color=NAVY)
add_para(doc,
    "Si detectas un error en tus marcajes, en tus justificaciones o en el ciclo de novedades, "
    "sigue esta ruta de escalamiento:",
    size=11)
add_num(doc, "Habla primero con tu supervisor directo (aparece en tu ficha).")
add_num(doc, "Si el supervisor no responde, escríbele a Recursos Humanos.")
add_num(doc, "Para problemas técnicos (la app no carga, el kiosco no reconoce a nadie, etc.), contacta al equipo de TI/Emergent con detalles y captura de pantalla.")

add_callout(doc, "RECORDATORIO FINAL",
    ["Este sistema busca hacer más transparente tu asistencia. Úsalo como aliado para dejar constancia oficial de tus tiempos, justificaciones y ausencias.",
     "Cualquier duda o mejora sugerida es bienvenida — habla con tu supervisor para canalizarla."],
    color_hex="EEF5FF", accent=NAVY)

# ---- Footer info ----
add_page_break(doc)
add_para(doc, "MegaSoft Computación, C.A.  —  Suite Corporativa de Asistencia — Manual del Empleado v1.0", size=9, color=GREY, align=WD_ALIGN_PARAGRAPH.CENTER)
add_para(doc, "Documento elaborado en febrero de 2026. Reproducción interna autorizada.", size=9, color=GREY, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)

doc.save(OUT)
print("OK:", OUT)
