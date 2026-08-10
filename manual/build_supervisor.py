"""Genera el manual del SUPERVISOR en Word (.docx).
Contenido: Mi Equipo, Novedades, Matriz de asistencia, Horarios y Reportes."""
from docx import Document
from _style import (
    apply_base_style, cover, h2, h3, body, bullets, steps,
    add_image, callout,
)


def page_break(doc):
    doc.add_page_break()

IMGS = "/app/manual/imgs"
OUT = "/app/manual/manual-supervisor-megasoft.docx"

doc = Document()
apply_base_style(doc)

# ================================================================
# COVER
# ================================================================
cover(
    doc,
    subtitle_top="MEGASOFT · SUITE CORPORATIVA DE ASISTENCIA",
    title="Manual del supervisor",
    subtitle_bottom="Gestión de equipo, novedades, matriz de asistencia, horarios y reportes · v1.1",
)

# ================================================================
# INTRO
# ================================================================
body(doc,
    "Como supervisor eres el primer nivel de control operativo del equipo. Este "
    "manual detalla los cinco módulos que usarás a diario para conocer quién marcó, "
    "quién llegó tarde, quién solicitó una novedad y qué reporte remitir a RRHH."
)
callout(doc,
    "🎯 Alcance del rol Supervisor: sólo ves y modificas información de los "
    "empleados que RRHH te ha asignado como equipo directo. El sistema aplica "
    "esta segregación automáticamente en todas las pantallas.",
    kind="info")

# ================================================================
# 1 · MI EQUIPO
# ================================================================
h2(doc, "1", "Mi equipo")

body(doc,
    "La pantalla “Mi equipo” es tu centro de control diario. Verás una tabla con "
    "todos los empleados a tu cargo y su patrón de marcas en los últimos días.")

add_image(doc, f"{IMGS}/sv-equipo.jpeg",
          "Vista general del equipo con estado por día")

h3(doc, "Lo que muestra cada fila")
bullets(doc, [
    "Foto, nombre y cargo del empleado.",
    "Departamento y — si tienes permiso especial — un selector para asignar horario en línea.",
    "Un cuadro por día con la marca del kiosco: hora de entrada y salida, o etiqueta “FALTA” si no marcó.",
    "Colores: verde (a tiempo), amarillo (dentro de tolerancia justificable), rojo (tardanza o descanso > 60 min).",
])

h3(doc, "Filtros disponibles")
bullets(doc, [
    "Rango: 7, 15 o 30 días atrás.",
    "Buscar por nombre para localizar a un empleado específico.",
    "Refrescar los datos con un clic si esperas nuevas marcas del día.",
])

h3(doc, "Asignar horario a un empleado (permiso especial)")
body(doc,
    "Si un administrador te dio el permiso “Puede crear horarios y asignarlos a los "
    "empleados de su equipo”, verás debajo del nombre un pequeño selector para "
    "cambiar el horario del empleado sin salir de la pantalla.")
steps(doc, [
    "Localiza al empleado en la tabla.",
    "Pulsa el selector de horario que aparece bajo su nombre.",
    "Elige el horario deseado (por ejemplo, “Turno Uno” o “Día Completo”).",
    "El cambio se guarda automáticamente — verás un aviso “Horario actualizado”.",
])

callout(doc,
    "⚠ No podrás asignar horarios a empleados que no están en tu equipo directo. "
    "Si necesitas cambiar el equipo de alguien, avisa a RRHH.",
    kind="warn")

# ================================================================
# 2 · NOVEDADES
# ================================================================
page_break(doc)
h2(doc, "2", "Novedades (vacaciones, reposos, permisos, visitas)")

body(doc,
    "El módulo Novedades centraliza toda excepción a la marca normal del kiosco: "
    "vacaciones, reposo médico, permisos, trabajo remoto, visitas a clientes, "
    "cita médica, etc. Como supervisor apruebas o rechazas las solicitudes de tu "
    "equipo antes de que impacten la nómina.")

add_image(doc, f"{IMGS}/sv-novedades.jpeg",
          "Bandeja de novedades — pestaña Pendientes")

h3(doc, "Pestañas de la pantalla")
bullets(doc, [
    "Pendientes — solicitudes esperando tu decisión. Es tu bandeja de trabajo.",
    "Historial — todo lo aprobado/rechazado en el pasado, con quién lo hizo y cuándo.",
    "Todas — vista completa combinada, útil para búsquedas puntuales.",
])

h3(doc, "Crear una novedad para un empleado")
steps(doc, [
    "Pulsa el botón amarillo “+ Nueva novedad” arriba a la derecha.",
    "Selecciona al empleado (sólo verás tu equipo directo).",
    "Elige el tipo: Vacaciones, Reposo, Permiso, Cita médica, Trabajo remoto, Visita a Clientes/Integradores.",
    "Define el rango de fechas. Si es un permiso de horas, marca “Sólo tramo horario” y coloca la hora de inicio y fin.",
    "Añade una nota explicativa (motivo, número de reposo médico, etc.).",
    "Adjunta comprobante si lo tienes (PDF o imagen) y pulsa “Guardar”. Queda en estado “Pendiente aprobación”.",
])

h3(doc, "Aprobar o rechazar una novedad")
steps(doc, [
    "En la pestaña “Pendientes”, revisa cada tarjeta (empleado, tipo, fechas, motivo, comprobante).",
    "Si todo es correcto, pulsa “Aprobar”. El sistema aplicará la novedad al reporte matricial y a nómina.",
    "Si falta información o el motivo no procede, pulsa “Rechazar” y escribe la razón — el empleado la verá.",
    "Puedes seleccionar varias tarjetas con la casilla y aprobar/rechazar en bloque.",
])

callout(doc,
    "🧾 Toda decisión queda registrada con tu nombre, fecha y hora. No se puede "
    "editar después: si te equivocas, crea otra novedad correctiva.",
    kind="note")

# ================================================================
# 3 · MATRIZ DE ASISTENCIA
# ================================================================
page_break(doc)
h2(doc, "3", "Matriz de asistencia")

body(doc,
    "La Matriz es la vista consolidada por empleado y día — la forma más rápida "
    "de detectar tardanzas, faltas y tramos incompletos. Se adapta al tipo de "
    "horario (1 o 2 bloques) y sirve como reporte oficial para RRHH.")

add_image(doc, f"{IMGS}/sv-matriz.jpeg",
          "Reporte matricial de asistencia — vista de 2 bloques")

h3(doc, "Filtros — de arriba a abajo")
bullets(doc, [
    "Desde / Hasta — por defecto se abre con el día de hoy. Cambia el rango si necesitas.",
    "Tipo de horario — por defecto muestra el primer horario de 2 bloques (la mayoría del personal). Cámbialo para consultar Turnos Uno/Dos/Nocturnos.",
    "Sede — filtra por sede física (útil si hay varias sedes con el mismo turno).",
    "Departamento — el sistema te muestra sólo los departamentos donde tienes gente.",
    "Empleado — para revisar a uno solo.",
])

h3(doc, "Cómo leer la matriz")
bullets(doc, [
    "Cada fila es un empleado; cada columna es un día del rango.",
    "Dentro de la celda del día se muestran las marcas: E1 (entrada bloque 1), S1 (salida), E2, S2. La hora sale en negro si está dentro de la tolerancia y en rojo si es tardanza o descanso > 60 min.",
    "“FALTA” en rojo indica que ese día no hubo ninguna marca ni novedad justificada.",
    "Si hay una novedad, la celda queda en color pastel: azul (vacaciones), morado (reposo), verde (trabajo remoto), etc.",
    "Cursiva en ámbar significa una salida que el sistema auto-cerró a las 23:59 (el empleado no marcó salida).",
])

h3(doc, "Totales por empleado (columnas de la derecha)")
bullets(doc, [
    "MIN. PERD. — minutos perdidos por llegar tarde en el rango consultado.",
    "T-J — Tardanzas justificadas (dentro de la ventana de justificación).",
    "T-NJ — Tardanzas NO justificadas.",
    "NOVEDADES — cantidad de novedades aplicadas.",
    "FALTAS — días sin marca ni novedad.",
])

h3(doc, "Exportar")
bullets(doc, [
    "PDF — formato listo para imprimir o enviar por correo, con logo y firma de fecha.",
    "Excel — hoja de cálculo con todos los datos, ideal para nómina o análisis propio.",
])

callout(doc,
    "🔎 Si un empleado marca en una sede distinta a la suya (ej. estaba de visita "
    "y usó otro kiosco), la celda tendrá un borde punteado — te avisa del "
    "“site_mismatch” para que valides el caso.",
    kind="tip")

# ================================================================
# 4 · HORARIOS
# ================================================================
page_break(doc)
h2(doc, "4", "Horarios (permiso especial)")

body(doc,
    "Este módulo sólo está disponible si un administrador te otorgó el permiso "
    "“Puede crear horarios y asignarlos a los empleados de su equipo”. Aquí "
    "defines los turnos que luego asignarás a tus empleados desde “Mi equipo”.")

add_image(doc, f"{IMGS}/sv-horarios.jpeg",
          "Listado de horarios · turnos de 1 y 2 bloques")

h3(doc, "Anatomía de un horario")
bullets(doc, [
    "Nombre — cómo lo verás en las listas (ej. “Turno Uno”, “Día Completo”).",
    "Bloques — 1 bloque (entrada y salida únicas) o 2 bloques (mañana + tarde con descanso intermedio).",
    "Horas — inicio y fin de cada bloque (formato 24 h o AM/PM).",
    "Tolerancia general — minutos que puede llegar tarde sin marcar tardanza (típicamente 10 min).",
    "Ventana de justificación — minutos adicionales en los que la tardanza aún se considera justificable con novedad (típicamente 20 min).",
])

h3(doc, "Crear un horario nuevo")
steps(doc, [
    "Pulsa “+ Nuevo horario” arriba a la derecha.",
    "Escribe un nombre claro (ej. “Guardia Fin de Semana”).",
    "Elige 1 o 2 bloques según corresponda.",
    "Rellena las horas de cada bloque.",
    "Define la tolerancia y la ventana de justificación (los valores por defecto suelen bastar).",
    "Guarda. El horario queda disponible para asignar en “Mi equipo” o en la ficha del empleado.",
])

callout(doc,
    "🧱 No borres un horario si aún hay empleados asignados a él — el sistema "
    "impedirá la eliminación. Primero reasigna a esos empleados.",
    kind="warn")

# ================================================================
# 5 · REPORTES
# ================================================================
page_break(doc)
h2(doc, "5", "Reportes")

body(doc,
    "El módulo Reportes es una vista transaccional: cada fila es una marca "
    "individual (entrada, salida o corrección). Se usa para auditar movimientos "
    "puntuales, cruzar con RRHH o exportar a nómina.")

add_image(doc, f"{IMGS}/sv-reportes.jpeg",
          "Reportes de asistencia con tarjetas resumen y filtros")

h3(doc, "Tarjetas resumen (parte superior)")
bullets(doc, [
    "Entradas — total de marcas de entrada en el rango.",
    "Salidas — total de marcas de salida.",
    "Tardanzas — cuántas entradas se marcaron fuera de la tolerancia.",
    "Con justificación — cuántas de esas tardanzas ya tienen una novedad asociada.",
])

h3(doc, "Filtros")
bullets(doc, [
    "Desde / Hasta — rango de fechas.",
    "Departamento y Empleado — para acotar a un grupo o persona.",
    "Sede — para separar marcas por sede física.",
    "Tipo — Entradas, Salidas o ambas.",
    "Estado — A tiempo, Tarde, Con novedad, Auto-cerrada.",
])

h3(doc, "Descargar CSV")
body(doc,
    "El botón “Exportar CSV” genera un archivo con TODAS las marcas filtradas — "
    "listo para abrir en Excel o subir a los sistemas de nómina.")

callout(doc,
    "📅 Recomendación: exporta al inicio de cada quincena filtrando “desde el "
    "día 1 hasta hoy” y guarda el CSV en la carpeta compartida de RRHH.",
    kind="tip")

# ================================================================
# 6 · CIERRE
# ================================================================
page_break(doc)
h2(doc, "6", "Buenas prácticas del supervisor")

bullets(doc, [
    "Revisa “Novedades → Pendientes” al menos una vez al día.",
    "Consulta “Mi equipo” en la mañana para detectar quién no marcó entrada.",
    "Usa la Matriz semanal para conversar tardanzas recurrentes con tu equipo.",
    "Antes de enviar reportes a RRHH, valida rápido las FALTAS con el empleado — a veces olvidaron marcar.",
    "Si un empleado no logra entrar al sistema (contraseña olvidada, rostro que no lo reconoce, kiosco caído) escríbele a RRHH — ellos pueden restablecer.",
])

callout(doc,
    "🚨 En emergencia (kiosco colgado, sede pegada): pide a un administrador "
    "que abra Ajustes → “Kioscos activos por sede” → “Liberar sede”. Es el "
    "camino oficial para reasignar el kiosco sin esperar al TTL.",
    kind="warn")

# ================================================================
# SAVE
# ================================================================
doc.save(OUT)
print(f"OK · {OUT}")
