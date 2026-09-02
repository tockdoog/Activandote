# backend/app/routers/dashboard.py
# Endpoints del panel estadístico: métricas globales, análisis del entrenador
# y exportación de reportes globales en Excel y PDF.
# El endpoint /network-info usa HOST_IP inyectada por los scripts de lanzamiento.

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import date, timedelta
import logging
import socket
import os
import io

# Librerías de exportación
from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.evaluation import Evaluation
from app.schemas import DashboardStats
from app.utils.security import get_current_active_user
# Función que determina si un paciente tiene un consentimiento (Habeas Data)
# vigente y válido — se reutiliza la misma lógica que usa el módulo de consentimiento
from app.utils.consent import tiene_consentimiento_valido

# -----------------------------------------------
# Configuración del router del dashboard
# -----------------------------------------------
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = logging.getLogger(__name__)

# -----------------------------------------------
# Paleta de colores corporativa FitPro — Verde y blanco, estética de salud
# (misma paleta que frontend/css/main.css: --verde-primario, --verde-oscuro, etc.)
# Para uso en reportes Excel y PDF.
# El rojo se reserva EXCLUSIVAMENTE para indicadores de alerta/pendiente,
# igual que --rojo-alerta en main.css — nunca como color de marca.
# -----------------------------------------------
COLOR_VERDE_PRIMARIO = "16A34A"   # Verde primario — encabezados y acentos de marca
COLOR_VERDE_OSCURO   = "15803D"   # Verde oscuro — encabezados de sección
COLOR_VERDE_SUAVE_BG = "DCFCE7"   # Verde muy suave — fondos de tarjetas KPI
COLOR_VERDE_BORDE    = "86EFAC"   # Verde medio — bordes decorativos
COLOR_GRIS_OSCURO    = "374E37"   # Gris verdoso oscuro — subtítulos
COLOR_GRIS_MEDIO     = "516651"   # Gris verdoso medio — texto secundario
COLOR_GRIS_CLARO     = "F4F8F4"   # Gris muy claro — filas alternas
COLOR_BLANCO         = "FFFFFF"   # Blanco puro — celdas de datos
COLOR_ALERTA_ROJO    = "EF4444"   # Rojo — SOLO para indicadores de alerta o pendiente
COLOR_ALERTA_BG      = "FEE2E2"   # Rojo muy claro — resaltar filas con alerta
COLOR_ALERTA_BORDE   = "FCA5A5"   # Rojo medio — bordes de celdas de alerta
COLOR_EXCELENTE      = "DCFCE7"   # Verde muy claro — condición excelente / cumplimiento
COLOR_REGULAR        = "FFF3E0"   # Naranja muy claro — condición regular
COLOR_VERDE_TEXTO    = "15803D"   # Verde texto — indicador de "OK" (Habeas Data aceptado)


# =============================================================
# ENDPOINTS EXISTENTES
# =============================================================

@router.get("/stats", response_model=DashboardStats)
async def obtener_estadisticas_globales(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna estadísticas globales del entrenador autenticado.
    Incluye conteos, promedios e indicadores clave del mes actual.
    """
    trainer_id = current_user.id
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    # Conteo total de pacientes registrados (activos e inactivos)
    total_pacientes = db.query(Patient).filter(
        Patient.trainer_id == trainer_id
    ).count()

    # Solo pacientes con estado activo actualmente
    pacientes_activos = db.query(Patient).filter(
        Patient.trainer_id == trainer_id,
        Patient.is_active == True,
        Patient.estado == "activo"
    ).count()

    # Total histórico de evaluaciones del entrenador
    total_evaluaciones = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id
    ).count()

    # Evaluaciones registradas en el mes en curso
    evaluaciones_mes = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.fecha_evaluacion >= inicio_mes
    ).count()

    # Cantidad de pacientes con al menos una alerta activa
    pacientes_con_alerta = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.tiene_alerta == True
    ).distinct(Evaluation.patient_id).count()

    # Promedio de IMC de todas las evaluaciones con IMC registrado
    promedio_imc = db.query(func.avg(Evaluation.imc)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.imc.isnot(None)
    ).scalar()

    # Promedio de porcentaje de grasa corporal
    promedio_grasa = db.query(func.avg(Evaluation.porcentaje_grasa)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.porcentaje_grasa.isnot(None)
    ).scalar()

    return DashboardStats(
        total_pacientes=total_pacientes,
        pacientes_activos=pacientes_activos,
        total_evaluaciones=total_evaluaciones,
        evaluaciones_este_mes=evaluaciones_mes,
        pacientes_con_alerta=pacientes_con_alerta,
        promedio_imc=round(float(promedio_imc), 2) if promedio_imc else None,
        promedio_grasa=round(float(promedio_grasa), 2) if promedio_grasa else None
    )


@router.get("/evoluciones")
async def obtener_evolucion_mensual(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna el número de evaluaciones registradas por mes (últimos 12 meses).
    """
    hoy = date.today()
    hace_12_meses = hoy - timedelta(days=365)

    # Agrupar evaluaciones por mes y año dentro del rango de 12 meses
    evaluaciones_por_mes = db.query(
        extract("year",  Evaluation.fecha_evaluacion).label("anio"),
        extract("month", Evaluation.fecha_evaluacion).label("mes"),
        func.count(Evaluation.id).label("total")
    ).filter(
        Evaluation.trainer_id == current_user.id,
        Evaluation.fecha_evaluacion >= hace_12_meses
    ).group_by("anio", "mes").order_by("anio", "mes").all()

    # Nombres cortos de meses en español para el eje X de la gráfica
    meses_es = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
    }

    return {
        "datos": [
            {
                "periodo": f"{meses_es[int(r.mes)]} {int(r.anio)}",
                "total_evaluaciones": r.total
            }
            for r in evaluaciones_por_mes
        ]
    }


@router.get("/alertas-recientes")
async def obtener_alertas_recientes(
    limite: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna las evaluaciones más recientes que tienen alertas activas.
    """
    # Unir evaluaciones con el nombre del paciente, filtrar alertas activas
    alertas = db.query(Evaluation, Patient.nombre_completo).join(
        Patient, Evaluation.patient_id == Patient.id
    ).filter(
        Evaluation.trainer_id == current_user.id,
        Evaluation.tiene_alerta == True
    ).order_by(
        Evaluation.fecha_evaluacion.desc()
    ).limit(limite).all()

    return {
        "alertas": [
            {
                "evaluacion_id": eval.id,
                "patient_id":    eval.patient_id,
                "nombre_paciente": nombre,
                "fecha":         str(eval.fecha_evaluacion),
                "detalle":       eval.detalle_alerta
            }
            for eval, nombre in alertas
        ]
    }


@router.get("/top-pacientes")
async def obtener_top_pacientes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna los 5 pacientes con más evaluaciones registradas.
    """
    # Contar evaluaciones por paciente activo y ordenar de mayor a menor
    top = db.query(
        Patient.id,
        Patient.nombre_completo,
        func.count(Evaluation.id).label("total_evaluaciones")
    ).join(
        Evaluation, Patient.id == Evaluation.patient_id, isouter=True
    ).filter(
        Patient.trainer_id == current_user.id,
        Patient.is_active == True
    ).group_by(
        Patient.id, Patient.nombre_completo
    ).order_by(
        func.count(Evaluation.id).desc()
    ).limit(5).all()

    return {
        "top_pacientes": [
            {
                "id":                r.id,
                "nombre":            r.nombre_completo,
                "total_evaluaciones": r.total_evaluaciones
            }
            for r in top
        ]
    }


# =============================================================
# ENDPOINT NUEVO: DATOS DEL REPORTE GLOBAL (JSON)
# Usado por el frontend para la previsualización antes de exportar
# =============================================================

@router.get("/reporte-global")
async def obtener_datos_reporte_global(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna el conjunto completo de datos para el reporte global:
    - Resumen estadístico del entrenador
    - Lista de pacientes con contacto, talla/peso, última evaluación,
      estado y estado de aceptación de Habeas Data
    - Evolución mensual de los últimos 12 meses
    - Top 5 pacientes más evaluados
    - Listado de alertas activas
    Usado como fuente de datos para los reportes Excel y PDF.
    """
    trainer_id = current_user.id
    hoy = date.today()
    inicio_mes = hoy.replace(day=1)
    hace_12_meses = hoy - timedelta(days=365)

    # ─── Resumen estadístico ───────────────────────────────────────────────
    total_pacientes = db.query(Patient).filter(
        Patient.trainer_id == trainer_id
    ).count()

    pacientes_activos = db.query(Patient).filter(
        Patient.trainer_id == trainer_id,
        Patient.is_active == True,
        Patient.estado == "activo"
    ).count()

    total_evaluaciones = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id
    ).count()

    evaluaciones_mes = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.fecha_evaluacion >= inicio_mes
    ).count()

    pacientes_con_alerta = db.query(Evaluation).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.tiene_alerta == True
    ).distinct(Evaluation.patient_id).count()

    promedio_imc = db.query(func.avg(Evaluation.imc)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.imc.isnot(None)
    ).scalar()

    promedio_grasa = db.query(func.avg(Evaluation.porcentaje_grasa)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.porcentaje_grasa.isnot(None)
    ).scalar()

    promedio_peso = db.query(func.avg(Evaluation.peso_kg)).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.peso_kg.isnot(None)
    ).scalar()

    # ─── Lista de pacientes con su última evaluación ───────────────────────
    # Subconsulta: id de la última evaluación por paciente
    subq = db.query(
        Evaluation.patient_id,
        func.max(Evaluation.fecha_evaluacion).label("ultima_fecha")
    ).filter(
        Evaluation.trainer_id == trainer_id
    ).group_by(Evaluation.patient_id).subquery()

    # Unir pacientes con la última evaluación disponible
    pacientes_raw = db.query(Patient, Evaluation).outerjoin(
        subq,
        Patient.id == subq.c.patient_id
    ).outerjoin(
        Evaluation,
        (Evaluation.patient_id == subq.c.patient_id) &
        (Evaluation.fecha_evaluacion == subq.c.ultima_fecha)
    ).filter(
        Patient.trainer_id == trainer_id
    ).order_by(Patient.nombre_completo).all()

    # Construir lista serializable de pacientes
    pacientes_lista = []
    for paciente, ultima_eval in pacientes_raw:
        entrada = {
            "id":               paciente.id,
            "nombre":           paciente.nombre_completo,
            "edad":             paciente.edad,
            "genero":           paciente.genero.value if paciente.genero else "—",
            "estado":           paciente.estado.value if paciente.estado else "—",
            # --- Contacto (requerido en el consolidado) ---
            "telefono":         paciente.telefono,
            "correo":           paciente.correo,
            # --- Datos físicos iniciales ---
            "talla_metros":     paciente.talla_metros,
            "peso_inicial_kg":  paciente.peso_inicial_kg,
            "fecha_ingreso":    str(paciente.fecha_ingreso) if paciente.fecha_ingreso else "—",
            # Datos de la última evaluación (None si no tiene)
            "ultima_evaluacion": str(ultima_eval.fecha_evaluacion) if ultima_eval else None,
            "peso_actual_kg":    ultima_eval.peso_kg           if ultima_eval else None,
            "imc":               round(ultima_eval.imc, 2)     if ultima_eval and ultima_eval.imc else None,
            "porcentaje_grasa":  ultima_eval.porcentaje_grasa  if ultima_eval else None,
            "condicion_fisica":  ultima_eval.condicion_fisica.value if ultima_eval and ultima_eval.condicion_fisica else None,
            "tiene_alerta":      ultima_eval.tiene_alerta      if ultima_eval else False,
            "detalle_alerta":    ultima_eval.detalle_alerta     if ultima_eval else None,
            "total_evaluaciones": db.query(func.count(Evaluation.id)).filter(
                Evaluation.patient_id == paciente.id
            ).scalar(),
            # --- Estado de Habeas Data (requerido en el consolidado) ---
            "habeas_data_aceptado": tiene_consentimiento_valido(db, paciente.id)
        }
        pacientes_lista.append(entrada)

    # Conteo de pacientes con Habeas Data vigente, para el resumen y las KPI
    pacientes_habeas_data_ok = sum(1 for p in pacientes_lista if p["habeas_data_aceptado"])

    # ─── Evolución mensual ─────────────────────────────────────────────────
    evoluciones_raw = db.query(
        extract("year",  Evaluation.fecha_evaluacion).label("anio"),
        extract("month", Evaluation.fecha_evaluacion).label("mes"),
        func.count(Evaluation.id).label("total")
    ).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.fecha_evaluacion >= hace_12_meses
    ).group_by("anio", "mes").order_by("anio", "mes").all()

    meses_es = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
    }

    evolucion_lista = [
        {
            "periodo": f"{meses_es[int(r.mes)]} {int(r.anio)}",
            "total":   r.total
        }
        for r in evoluciones_raw
    ]

    # ─── Top 5 pacientes ───────────────────────────────────────────────────
    top_raw = db.query(
        Patient.nombre_completo,
        func.count(Evaluation.id).label("total_evaluaciones")
    ).join(
        Evaluation, Patient.id == Evaluation.patient_id, isouter=True
    ).filter(
        Patient.trainer_id == trainer_id,
        Patient.is_active == True
    ).group_by(
        Patient.id, Patient.nombre_completo
    ).order_by(
        func.count(Evaluation.id).desc()
    ).limit(5).all()

    top_lista = [
        {"nombre": r.nombre_completo, "total": r.total_evaluaciones}
        for r in top_raw
    ]

    # ─── Alertas activas ───────────────────────────────────────────────────
    alertas_raw = db.query(Evaluation, Patient.nombre_completo).join(
        Patient, Evaluation.patient_id == Patient.id
    ).filter(
        Evaluation.trainer_id == trainer_id,
        Evaluation.tiene_alerta == True
    ).order_by(Evaluation.fecha_evaluacion.desc()).limit(20).all()

    alertas_lista = [
        {
            "nombre":  nombre,
            "fecha":   str(ev.fecha_evaluacion),
            "detalle": ev.detalle_alerta or "Sin detalle"
        }
        for ev, nombre in alertas_raw
    ]

    # ─── Respuesta final ───────────────────────────────────────────────────
    return {
        "generado_en":   str(hoy),
        "entrenador":    current_user.nombre_completo,
        "resumen": {
            "total_pacientes":      total_pacientes,
            "pacientes_activos":    pacientes_activos,
            "total_evaluaciones":   total_evaluaciones,
            "evaluaciones_mes":     evaluaciones_mes,
            "pacientes_con_alerta": pacientes_con_alerta,
            "promedio_imc":   round(float(promedio_imc), 2)   if promedio_imc   else None,
            "promedio_grasa": round(float(promedio_grasa), 2) if promedio_grasa else None,
            "promedio_peso":  round(float(promedio_peso), 2)  if promedio_peso  else None,
            "pacientes_habeas_data_ok": pacientes_habeas_data_ok,
        },
        "pacientes":     pacientes_lista,
        "evolucion":     evolucion_lista,
        "top_pacientes": top_lista,
        "alertas":       alertas_lista
    }


# =============================================================
# ENDPOINT NUEVO: EXPORTAR REPORTE GLOBAL EN EXCEL
# Genera un libro .xlsx con múltiples hojas y diseño deportivo
# =============================================================

@router.get("/reporte-global/excel")
async def exportar_reporte_global_excel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Genera y descarga el reporte global en formato Excel (.xlsx).
    El archivo contiene 4 hojas:
      1. Resumen — estadísticas clave con diseño de dashboard
      2. Pacientes — tabla completa: datos, contacto, talla/peso,
         última evaluación, estado y Habeas Data
      3. Evolución — evaluaciones por mes (últimos 12 meses)
      4. Alertas — listado de pacientes con alertas activas
    """
    # ─── Obtener datos reutilizando la lógica del endpoint JSON ───────────
    datos = await obtener_datos_reporte_global(db=db, current_user=current_user)

    # ─── Crear libro Excel ────────────────────────────────────────────────
    wb = Workbook()

    # ─── Estilos reutilizables ─────────────────────────────────────────────

    # Bordes para las celdas de datos
    borde_fino = Border(
        left=Side(style="thin",   color="E0E0E0"),
        right=Side(style="thin",  color="E0E0E0"),
        top=Side(style="thin",    color="E0E0E0"),
        bottom=Side(style="thin", color="E0E0E0")
    )
    borde_medio = Border(
        left=Side(style="medium",   color=COLOR_VERDE_PRIMARIO),
        right=Side(style="medium",  color=COLOR_VERDE_PRIMARIO),
        top=Side(style="medium",    color=COLOR_VERDE_PRIMARIO),
        bottom=Side(style="medium", color=COLOR_VERDE_PRIMARIO)
    )

    def estilo_encabezado_principal(celda, texto):
        """Aplica estilo de título principal verde/blanco/negrita"""
        celda.value     = texto
        celda.font      = Font(name="Calibri", bold=True, size=18,
                               color=COLOR_BLANCO, italic=False)
        celda.fill      = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)
        celda.alignment = Alignment(horizontal="left", vertical="center",
                                    indent=2)

    def estilo_encabezado_seccion(celda, texto):
        """Encabezado de sección: fondo verde oscuro, texto blanco"""
        celda.value     = texto
        celda.font      = Font(name="Calibri", bold=True, size=11,
                               color=COLOR_BLANCO)
        celda.fill      = PatternFill("solid", fgColor=COLOR_VERDE_OSCURO)
        celda.alignment = Alignment(horizontal="left", vertical="center",
                                    indent=1)

    def estilo_columna(celda, texto):
        """Encabezado de columna: fondo verde, texto blanco, negrita"""
        celda.value     = texto
        celda.font      = Font(name="Calibri", bold=True, size=10,
                               color=COLOR_BLANCO)
        celda.fill      = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)
        celda.alignment = Alignment(horizontal="center", vertical="center",
                                    wrap_text=True)
        celda.border    = borde_fino

    def estilo_dato(celda, valor, par=True, alinear="center"):
        """Celda de dato: fondo alterno blanco/gris muy claro"""
        celda.value     = valor
        celda.font      = Font(name="Calibri", size=10, color="1F3A1F")
        fondo = COLOR_BLANCO if par else COLOR_GRIS_CLARO
        celda.fill      = PatternFill("solid", fgColor=fondo)
        celda.alignment = Alignment(horizontal=alinear, vertical="center")
        celda.border    = borde_fino

    def estilo_kpi(celda, valor, subtitulo=False):
        """Tarjeta KPI: valor grande o subtítulo pequeño"""
        celda.value = valor
        if subtitulo:
            celda.font      = Font(name="Calibri", size=9,
                                   color=COLOR_GRIS_OSCURO, italic=True)
            celda.fill      = PatternFill("solid", fgColor=COLOR_VERDE_SUAVE_BG)
            celda.alignment = Alignment(horizontal="center", vertical="center")
        else:
            celda.font      = Font(name="Calibri", bold=True, size=20,
                                   color=COLOR_VERDE_PRIMARIO)
            celda.fill      = PatternFill("solid", fgColor=COLOR_VERDE_SUAVE_BG)
            celda.alignment = Alignment(horizontal="center", vertical="center")
        celda.border = Border(
            left=Side(style="thin",   color=COLOR_VERDE_BORDE),
            right=Side(style="thin",  color=COLOR_VERDE_BORDE),
            top=Side(style="thin",    color=COLOR_VERDE_BORDE),
            bottom=Side(style="thin", color=COLOR_VERDE_BORDE)
        )

    # =========================================================
    # HOJA 1: RESUMEN
    # =========================================================
    ws1 = wb.active
    ws1.title = "Resumen"
    ws1.sheet_view.showGridLines = False

    # Ancho de columnas para la hoja de resumen
    for col_idx, ancho in enumerate([3, 18, 18, 18, 18, 18, 18, 3], start=1):
        ws1.column_dimensions[get_column_letter(col_idx)].width = ancho

    # Encabezado principal
    ws1.row_dimensions[2].height = 48
    ws1.merge_cells("B2:G2")
    estilo_encabezado_principal(
        ws1["B2"],
        f"🏋️  FITPRO — REPORTE GLOBAL DE RENDIMIENTO"
    )

    # Subtítulo con fecha y entrenador
    ws1.row_dimensions[3].height = 22
    ws1.merge_cells("B3:G3")
    ws1["B3"].value     = (f"Entrenador: {datos['entrenador']}  |  "
                           f"Generado: {datos['generado_en']}")
    ws1["B3"].font      = Font(name="Calibri", size=10,
                               color=COLOR_BLANCO, italic=True)
    ws1["B3"].fill      = PatternFill("solid", fgColor=COLOR_GRIS_OSCURO)
    ws1["B3"].alignment = Alignment(horizontal="left", vertical="center",
                                    indent=2)

    # Separador visual
    ws1.row_dimensions[4].height = 8
    for col in "BCDEFG":
        ws1[f"{col}4"].fill = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)

    # Etiqueta de sección KPI
    ws1.row_dimensions[6].height = 22
    ws1.merge_cells("B6:G6")
    estilo_encabezado_seccion(ws1["B6"], "  INDICADORES CLAVE DE RENDIMIENTO")

    # Tarjetas KPI — Fila 7 (valores) y fila 8 (etiquetas)
    ws1.row_dimensions[7].height = 52
    ws1.row_dimensions[8].height = 24

    resumen = datos["resumen"]
    kpis = [
        (resumen["total_pacientes"],       "Total\nPacientes"),
        (resumen["pacientes_activos"],      "Pacientes\nActivos"),
        (resumen["total_evaluaciones"],     "Total\nEvaluaciones"),
        (resumen["evaluaciones_mes"],       "Eval.\nEste Mes"),
        (resumen["pacientes_con_alerta"],   "Con\nAlerta"),
        (f"{resumen['promedio_imc'] or '—'}", "IMC\nPromedio"),
    ]
    cols_kpi = ["B", "C", "D", "E", "F", "G"]

    for idx, (valor, etiqueta) in enumerate(kpis):
        col = cols_kpi[idx]
        estilo_kpi(ws1[f"{col}7"], valor)
        estilo_kpi(ws1[f"{col}8"], etiqueta, subtitulo=True)

    # Separador visual
    ws1.row_dimensions[9].height = 6
    for col in "BCDEFG":
        ws1[f"{col}9"].fill = PatternFill("solid", fgColor=COLOR_VERDE_BORDE)

    # Sección Top 5 Pacientes
    ws1.row_dimensions[11].height = 22
    ws1.merge_cells("B11:G11")
    estilo_encabezado_seccion(ws1["B11"], "  TOP 5 PACIENTES POR EVALUACIONES")

    # Encabezados de la mini-tabla
    ws1.row_dimensions[12].height = 22
    for col, texto in zip(["B", "C", "D", "E", "F", "G"],
                          ["#", "Paciente", "", "Evaluaciones", "", ""]):
        estilo_columna(ws1[f"{col}12"], texto)

    # Datos del top 5
    for i, pac in enumerate(datos["top_pacientes"], start=1):
        fila = 12 + i
        ws1.row_dimensions[fila].height = 20
        par = (i % 2 == 0)
        estilo_dato(ws1[f"B{fila}"], i,         par)
        ws1.merge_cells(f"C{fila}:E{fila}")
        estilo_dato(ws1[f"C{fila}"], pac["nombre"], par, "left")
        ws1.merge_cells(f"F{fila}:G{fila}")
        estilo_dato(ws1[f"F{fila}"], pac["total"], par)

    # Sección Cumplimiento Habeas Data — resumen rápido antes de la evolución mensual
    fila_cump = 12 + len(datos["top_pacientes"]) + 3
    ws1.row_dimensions[fila_cump].height = 22
    ws1.merge_cells(f"B{fila_cump}:G{fila_cump}")
    estilo_encabezado_seccion(ws1[f"B{fila_cump}"], "  CUMPLIMIENTO HABEAS DATA")

    fila_cump += 1
    ws1.row_dimensions[fila_cump].height = 28
    ws1.merge_cells(f"B{fila_cump}:G{fila_cump}")
    ok_habeas   = resumen.get("pacientes_habeas_data_ok", 0)
    total_pac_r = resumen.get("total_pacientes", 0)
    completo    = total_pac_r > 0 and ok_habeas == total_pac_r
    ws1[f"B{fila_cump}"].value = (
        f"{ok_habeas} de {total_pac_r} pacientes con consentimiento de "
        f"Habeas Data vigente"
    )
    ws1[f"B{fila_cump}"].font = Font(
        name="Calibri", size=11, bold=True,
        color=COLOR_VERDE_TEXTO if completo else COLOR_ALERTA_ROJO
    )
    ws1[f"B{fila_cump}"].fill = PatternFill(
        "solid", fgColor=COLOR_EXCELENTE if completo else COLOR_ALERTA_BG
    )
    ws1[f"B{fila_cump}"].alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # Sección Evolución mensual
    fila_evol = fila_cump + 3
    ws1.row_dimensions[fila_evol].height = 22
    ws1.merge_cells(f"B{fila_evol}:G{fila_evol}")
    estilo_encabezado_seccion(ws1[f"B{fila_evol}"],
                              "  EVALUACIONES POR MES — ÚLTIMOS 12 MESES")

    fila_evol += 1
    for col, texto in zip(["B", "C", "D", "E", "F", "G"],
                          ["Período", "Evaluaciones", "", "", "", ""]):
        ws1.row_dimensions[fila_evol].height = 22
        estilo_columna(ws1[f"{col}{fila_evol}"], texto)

    for i, mes_dato in enumerate(datos["evolucion"], start=1):
        fila = fila_evol + i
        ws1.row_dimensions[fila].height = 20
        par = (i % 2 == 0)
        estilo_dato(ws1[f"B{fila}"], mes_dato["periodo"], par, "left")
        ws1.merge_cells(f"C{fila}:G{fila}")
        estilo_dato(ws1[f"C{fila}"], mes_dato["total"], par)

    # Pie de página
    fila_pie = fila_evol + len(datos["evolucion"]) + 3
    ws1.merge_cells(f"B{fila_pie}:G{fila_pie}")
    ws1[f"B{fila_pie}"].value     = "FitPro — Sistema de Gestión Deportiva  |  Reporte confidencial"
    ws1[f"B{fila_pie}"].font      = Font(name="Calibri", size=8,
                                         color=COLOR_GRIS_MEDIO, italic=True)
    ws1[f"B{fila_pie}"].alignment = Alignment(horizontal="center")

    # =========================================================
    # HOJA 2: PACIENTES
    # =========================================================
    ws2 = wb.create_sheet("Pacientes")
    ws2.sheet_view.showGridLines = False

    # Ancho de columnas de la tabla de pacientes
    # A(margen) B-Nombre C-Edad D-Género E-Estado F-Teléfono G-Correo
    # H-Talla I-PesoIni J-ÚEval K-PesoAct L-IMC M-%Grasa N-Evaluaciones O-HabeasData P(margen)
    anchos_pac = [3, 24, 6, 10, 10, 13, 20, 8, 9, 9, 9, 7, 8, 9, 9, 3]
    for i, ancho in enumerate(anchos_pac, start=1):
        ws2.column_dimensions[get_column_letter(i)].width = ancho

    # Encabezado
    ws2.row_dimensions[2].height = 40
    ws2.merge_cells("B2:O2")
    estilo_encabezado_principal(ws2["B2"], "🏋️  FITPRO — LISTADO COMPLETO DE PACIENTES")

    ws2.row_dimensions[3].height = 18
    ws2.merge_cells("B3:O3")
    ws2["B3"].value     = (f"Entrenador: {datos['entrenador']}  |  "
                           f"Fecha: {datos['generado_en']}  |  "
                           f"Total: {len(datos['pacientes'])} pacientes")
    ws2["B3"].font      = Font(name="Calibri", size=9,
                               color=COLOR_BLANCO, italic=True)
    ws2["B3"].fill      = PatternFill("solid", fgColor=COLOR_GRIS_OSCURO)
    ws2["B3"].alignment = Alignment(horizontal="left", vertical="center",
                                    indent=2)

    # Separador
    ws2.row_dimensions[4].height = 6
    for c in range(2, 16):
        ws2.cell(4, c).fill = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)

    # Encabezados de columna
    cabeceras_pac = [
        "Nombre Completo", "Edad", "Género", "Estado", "Teléfono", "Correo",
        "Talla (m)", "Peso Ini. (kg)", "Ú. Eval.",
        "Peso Act. (kg)", "IMC", "% Grasa", "Evaluaciones", "Habeas Data"
    ]
    cols_pac = ["B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O"]

    ws2.row_dimensions[5].height = 28
    for col, cab in zip(cols_pac, cabeceras_pac):
        estilo_columna(ws2[f"{col}5"], cab)

    # Datos de pacientes
    for i, pac in enumerate(datos["pacientes"], start=1):
        fila = 5 + i
        ws2.row_dimensions[fila].height = 20
        par = (i % 2 == 0)

        # Detectar si tiene alerta para colorear la fila
        color_fila = COLOR_ALERTA_BG if pac.get("tiene_alerta") else (
            COLOR_BLANCO if par else COLOR_GRIS_CLARO
        )

        def dato_pac(celda_ref, valor, alinear="center"):
            c = ws2[celda_ref]
            c.value     = valor if valor is not None else "—"
            c.font      = Font(name="Calibri", size=9, color="1F3A1F",
                               bold=pac.get("tiene_alerta", False))
            c.fill      = PatternFill("solid", fgColor=color_fila)
            c.alignment = Alignment(horizontal=alinear, vertical="center")
            c.border    = borde_fino

        dato_pac(f"B{fila}", pac["nombre"], "left")
        dato_pac(f"C{fila}", pac["edad"])
        dato_pac(f"D{fila}", pac["genero"].capitalize())
        dato_pac(f"E{fila}", pac["estado"].capitalize())
        dato_pac(f"F{fila}", pac.get("telefono") or "—", "left")
        dato_pac(f"G{fila}", pac.get("correo") or "—", "left")
        dato_pac(f"H{fila}", pac["talla_metros"])
        dato_pac(f"I{fila}", pac["peso_inicial_kg"])
        dato_pac(f"J{fila}", pac["ultima_evaluacion"] or "Sin eval.")
        dato_pac(f"K{fila}", pac["peso_actual_kg"])
        dato_pac(f"L{fila}", pac["imc"])
        dato_pac(f"M{fila}", pac["porcentaje_grasa"])
        dato_pac(f"N{fila}", pac["total_evaluaciones"])
        dato_pac(f"O{fila}", "Sí" if pac.get("habeas_data_aceptado") else "No")

        # Colorear la celda de Habeas Data según cumplimiento (verde/rojo)
        celda_hd = ws2[f"O{fila}"]
        celda_hd.font = Font(
            name="Calibri", size=9, bold=True,
            color=COLOR_VERDE_TEXTO if pac.get("habeas_data_aceptado") else COLOR_ALERTA_ROJO
        )

    # Pie de página de la hoja pacientes
    fila_pie2 = 5 + len(datos["pacientes"]) + 2
    ws2.merge_cells(f"B{fila_pie2}:O{fila_pie2}")
    ws2[f"B{fila_pie2}"].value     = "★ Filas en rojo claro indican pacientes con alertas activas  |  FitPro Sistema Deportivo"
    ws2[f"B{fila_pie2}"].font      = Font(name="Calibri", size=8,
                                          color=COLOR_GRIS_MEDIO, italic=True)
    ws2[f"B{fila_pie2}"].alignment = Alignment(horizontal="center")

    # =========================================================
    # HOJA 3: EVOLUCIÓN MENSUAL
    # =========================================================
    ws3 = wb.create_sheet("Evolución Mensual")
    ws3.sheet_view.showGridLines = False

    for col_idx, ancho in enumerate([3, 20, 20, 3], start=1):
        ws3.column_dimensions[get_column_letter(col_idx)].width = ancho

    ws3.row_dimensions[2].height = 40
    ws3.merge_cells("B2:D2")
    estilo_encabezado_principal(ws3["B2"], "📅  EVALUACIONES POR MES")

    ws3.row_dimensions[3].height = 18
    ws3.merge_cells("B3:D3")
    ws3["B3"].value     = f"Últimos 12 meses  |  {datos['generado_en']}"
    ws3["B3"].font      = Font(name="Calibri", size=9,
                               color=COLOR_BLANCO, italic=True)
    ws3["B3"].fill      = PatternFill("solid", fgColor=COLOR_GRIS_OSCURO)
    ws3["B3"].alignment = Alignment(horizontal="left", vertical="center",
                                    indent=2)

    ws3.row_dimensions[4].height = 6
    for c in range(2, 5):
        ws3.cell(4, c).fill = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)

    ws3.row_dimensions[5].height = 26
    for col, cab in zip(["B", "C"], ["Período", "Evaluaciones"]):
        estilo_columna(ws3[f"{col}5"], cab)
        ws3[f"D5"].fill = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)

    # Calcular máximo para barras proporcionales
    max_eval = max((m["total"] for m in datos["evolucion"]), default=1)

    for i, mes_dato in enumerate(datos["evolucion"], start=1):
        fila = 5 + i
        ws3.row_dimensions[fila].height = 22
        par = (i % 2 == 0)
        estilo_dato(ws3[f"B{fila}"], mes_dato["periodo"], par, "left")
        estilo_dato(ws3[f"C{fila}"], mes_dato["total"], par)
        # Barra visual proporcional usando caracteres de bloque
        barra_len = int((mes_dato["total"] / max_eval) * 20) if max_eval > 0 else 0
        ws3[f"D{fila}"].value     = "█" * barra_len
        ws3[f"D{fila}"].font      = Font(name="Calibri", size=9,
                                          color=COLOR_VERDE_PRIMARIO)
        ws3[f"D{fila}"].fill      = PatternFill("solid",
                                                 fgColor=COLOR_BLANCO if par else COLOR_GRIS_CLARO)
        ws3[f"D{fila}"].alignment = Alignment(horizontal="left",
                                               vertical="center")
        ws3["D5"].width = 25
        ws3.column_dimensions["D"].width = 28

    # =========================================================
    # HOJA 4: ALERTAS
    # =========================================================
    ws4 = wb.create_sheet("Alertas Activas")
    ws4.sheet_view.showGridLines = False

    for col_idx, ancho in enumerate([3, 28, 16, 40, 3], start=1):
        ws4.column_dimensions[get_column_letter(col_idx)].width = ancho

    ws4.row_dimensions[2].height = 40
    ws4.merge_cells("B2:E2")
    estilo_encabezado_principal(ws4["B2"], "⚠️  PACIENTES CON ALERTAS ACTIVAS")

    ws4.row_dimensions[3].height = 18
    ws4.merge_cells("B3:E3")
    ws4["B3"].value     = (f"Total de alertas: {len(datos['alertas'])}  |  "
                           f"Fecha: {datos['generado_en']}")
    ws4["B3"].font      = Font(name="Calibri", size=9,
                               color=COLOR_BLANCO, italic=True)
    ws4["B3"].fill      = PatternFill("solid", fgColor=COLOR_GRIS_OSCURO)
    ws4["B3"].alignment = Alignment(horizontal="left", vertical="center",
                                    indent=2)

    ws4.row_dimensions[4].height = 6
    for c in range(2, 6):
        ws4.cell(4, c).fill = PatternFill("solid", fgColor=COLOR_VERDE_PRIMARIO)

    ws4.row_dimensions[5].height = 26
    for col, cab in zip(["B", "C", "D", "E"],
                        ["Paciente", "Fecha Evaluación", "Detalle de Alerta", ""]):
        estilo_columna(ws4[f"{col}5"], cab)

    if not datos["alertas"]:
        # Sin alertas: mostrar mensaje positivo
        ws4.row_dimensions[6].height = 30
        ws4.merge_cells("B6:E6")
        ws4["B6"].value     = "✅  Sin alertas activas — Todos los pacientes están en rangos saludables"
        ws4["B6"].font      = Font(name="Calibri", size=11,
                                   color=COLOR_GRIS_OSCURO, italic=True)
        ws4["B6"].alignment = Alignment(horizontal="center", vertical="center")
        ws4["B6"].fill      = PatternFill("solid", fgColor=COLOR_EXCELENTE)
    else:
        for i, alerta in enumerate(datos["alertas"], start=1):
            fila = 5 + i
            ws4.row_dimensions[fila].height = 22

            for col in ["B", "C", "D", "E"]:
                ws4[f"{col}{fila}"].fill   = PatternFill("solid",
                                                          fgColor=COLOR_ALERTA_BG)
                ws4[f"{col}{fila}"].border = borde_fino

            ws4[f"B{fila}"].value     = alerta["nombre"]
            ws4[f"B{fila}"].font      = Font(name="Calibri", size=10,
                                              color="1F3A1F", bold=True)
            ws4[f"B{fila}"].alignment = Alignment(horizontal="left",
                                                   vertical="center")

            ws4[f"C{fila}"].value     = alerta["fecha"]
            ws4[f"C{fila}"].font      = Font(name="Calibri", size=10,
                                              color="1F3A1F")
            ws4[f"C{fila}"].alignment = Alignment(horizontal="center",
                                                   vertical="center")

            ws4[f"D{fila}"].value     = alerta["detalle"]
            ws4[f"D{fila}"].font      = Font(name="Calibri", size=9,
                                              color="B71C1C")
            ws4[f"D{fila}"].alignment = Alignment(horizontal="left",
                                                   vertical="center",
                                                   wrap_text=True)

    # ─── Serializar y retornar el archivo ─────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nombre_archivo = (
        f"fitpro_reporte_global_"
        f"{datos['generado_en'].replace('-', '')}.xlsx"
    )

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={nombre_archivo}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# =============================================================
# ENDPOINT NUEVO: EXPORTAR REPORTE GLOBAL EN PDF
# Genera un PDF con diseño deportivo rojo/negro/blanco
# =============================================================

@router.get("/reporte-global/pdf")
async def exportar_reporte_global_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Genera y descarga el reporte global en formato PDF.
    Diseño deportivo horizontal (A4 apaisado) con paleta rojo/negro/blanco,
    necesario para que quepan todas las columnas del consolidado: datos,
    contacto, talla/peso, evaluaciones, estado y Habeas Data.
    Incluye portada, resumen estadístico, tabla de pacientes y alertas.
    """
    # Obtener datos reutilizando la lógica del endpoint JSON
    datos = await obtener_datos_reporte_global(db=db, current_user=current_user)

    buffer = io.BytesIO()

    # Documento PDF en A4 apaisado (landscape) — se necesita el ancho extra
    # para incluir teléfono, correo y Habeas Data sin amontonar el texto
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title="FitPro — Reporte Global",
        author=datos["entrenador"]
    )

    # ─── Paleta de colores ReportLab — Verde y blanco (estética de salud),
    # igual que frontend/css/main.css. El rojo se reserva exclusivamente
    # para indicadores de alerta real (fila con alerta, Habeas Data
    # pendiente, hoja de alertas), nunca como color de marca. ─────────────
    VERDE      = colors.HexColor("#16A34A")   # Verde primario — encabezados y acentos de marca
    VERDE_OSC  = colors.HexColor("#15803D")   # Verde oscuro — encabezados de sección
    GRIS_OS    = colors.HexColor("#374E37")   # Gris verdoso oscuro — subtítulos
    GRIS_CL    = colors.HexColor("#F4F8F4")   # Gris muy claro — filas alternas
    BLANCO     = colors.white
    VERDE_CL   = colors.HexColor("#DCFCE7")   # Verde muy suave — fondos de tarjetas KPI
    VERDE_MED  = colors.HexColor("#86EFAC")   # Verde medio — bordes decorativos
    VERDE_OK   = colors.HexColor("#15803D")   # Indicador semántico "OK" en Habeas Data
    ALERTA_ROJO = colors.HexColor("#EF4444")  # SOLO para indicadores de alerta o pendiente
    ALERTA_CL   = colors.HexColor("#FEE2E2")  # Fondo suave de alerta
    ALERTA_MED  = colors.HexColor("#FCA5A5")  # Borde/realce de alerta

    # ─── Estilos de párrafo ───────────────────────────────────────────────
    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        "titulo",
        fontSize=24, leading=30, textColor=BLANCO,
        fontName="Helvetica-Bold", alignment=TA_LEFT,
        leftIndent=8, spaceAfter=0
    )
    estilo_subtitulo = ParagraphStyle(
        "subtitulo",
        fontSize=9, leading=14, textColor=colors.HexColor("#CCCCCC"),
        fontName="Helvetica", alignment=TA_LEFT,
        leftIndent=8, spaceAfter=0
    )
    estilo_seccion = ParagraphStyle(
        "seccion",
        fontSize=11, leading=16, textColor=BLANCO,
        fontName="Helvetica-Bold", alignment=TA_LEFT,
        leftIndent=6, spaceAfter=2
    )
    estilo_nota = ParagraphStyle(
        "nota",
        fontSize=7, leading=10, textColor=GRIS_OS,
        fontName="Helvetica", alignment=TA_CENTER,
        spaceAfter=0
    )
    estilo_dato_tabla = ParagraphStyle(
        "dato_tabla",
        fontSize=8, leading=10, textColor=colors.HexColor("#1F3A1F"),
        fontName="Helvetica", alignment=TA_LEFT
    )

    # ─── Función para encabezado de sección ───────────────────────────────
    def tabla_seccion(titulo_texto):
        """Tabla de una fila como encabezado de sección con fondo verde oscuro"""
        t = Table([[Paragraph(titulo_texto, estilo_seccion)]],
                  colWidths=[doc.width])
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, -1), VERDE_OSC),
            ("TOPPADDING",  (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ]))
        return t

    # ─── Inicio del contenido ─────────────────────────────────────────────
    elementos = []
    resumen = datos["resumen"]
    ancho_total = doc.width

    # ── PORTADA / ENCABEZADO PRINCIPAL ────────────────────────────────────
    titulo_data = [[
        Paragraph("🏋️  FITPRO", estilo_titulo),
        Paragraph("REPORTE GLOBAL DE RENDIMIENTO", estilo_titulo)
    ]]
    tabla_titulo = Table(titulo_data,
                         colWidths=[ancho_total * 0.28, ancho_total * 0.72])
    tabla_titulo.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), VERDE),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_titulo)

    # Banda de subtítulo con datos del entrenador
    subtitulo_data = [[
        Paragraph(
            f"Entrenador: {datos['entrenador']}  |  "
            f"Generado: {datos['generado_en']}  |  "
            f"Pacientes: {resumen['total_pacientes']}  |  "
            f"Evaluaciones: {resumen['total_evaluaciones']}",
            estilo_subtitulo
        )
    ]]
    tabla_sub = Table(subtitulo_data, colWidths=[ancho_total])
    tabla_sub.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GRIS_OS),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabla_sub)
    elementos.append(Spacer(1, 0.4 * cm))

    # ── TARJETAS KPI ──────────────────────────────────────────────────────
    elementos.append(tabla_seccion("  INDICADORES CLAVE DE RENDIMIENTO"))
    elementos.append(Spacer(1, 0.2 * cm))

    estilo_kpi_num = ParagraphStyle(
        "kpi_num", fontSize=22, leading=26,
        textColor=VERDE, fontName="Helvetica-Bold",
        alignment=TA_CENTER, spaceAfter=0
    )
    estilo_kpi_lbl = ParagraphStyle(
        "kpi_lbl", fontSize=7, leading=9,
        textColor=GRIS_OS, fontName="Helvetica",
        alignment=TA_CENTER, spaceAfter=0
    )

    # 7 KPI en una fila horizontal (incluye cumplimiento de Habeas Data)
    total_pac_kpi = resumen["total_pacientes"] or 0
    ok_habeas_kpi = resumen.get("pacientes_habeas_data_ok", 0)
    pct_habeas    = round((ok_habeas_kpi / total_pac_kpi) * 100) if total_pac_kpi > 0 else 0

    kpi_lista = [
        (str(resumen["total_pacientes"]),       "TOTAL\nPACIENTES"),
        (str(resumen["pacientes_activos"]),      "PACIENTES\nACTIVOS"),
        (str(resumen["total_evaluaciones"]),     "TOTAL\nEVALUACIONES"),
        (str(resumen["evaluaciones_mes"]),       "EVAL.\nESTE MES"),
        (str(resumen["pacientes_con_alerta"]),   "CON\nALERTA"),
        (str(resumen["promedio_imc"] or "—"),    "IMC\nPROMEDIO"),
        (f"{pct_habeas}%",                       "HABEAS DATA\nCUMPLIDO"),
    ]

    kpi_row = [[Paragraph(num, estilo_kpi_num), Paragraph(lbl, estilo_kpi_lbl)]
               for num, lbl in kpi_lista]

    tabla_kpi = Table([kpi_row],
                      colWidths=[ancho_total / 7] * 7,
                      rowHeights=[1.6 * cm])
    tabla_kpi.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), VERDE_CL),
        ("BOX",           (0, 0), (-1, -1), 0.5, VERDE_MED),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, VERDE_MED),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabla_kpi)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── TABLA DE PACIENTES ────────────────────────────────────────────────
    elementos.append(tabla_seccion("  LISTADO DE PACIENTES — DATOS, CONTACTO Y HABEAS DATA"))
    elementos.append(Spacer(1, 0.2 * cm))

    estilo_cab_tabla = ParagraphStyle(
        "cab", fontSize=8, leading=10, textColor=BLANCO,
        fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    estilo_cel_tabla = ParagraphStyle(
        "cel", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#1F3A1F"),
        fontName="Helvetica", alignment=TA_LEFT
    )
    estilo_cel_c = ParagraphStyle(
        "celc", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#1F3A1F"),
        fontName="Helvetica", alignment=TA_CENTER
    )
    estilo_alerta_txt = ParagraphStyle(
        "alerta_txt", fontSize=7.5, leading=9.5,
        textColor=colors.HexColor("#B71C1C"),
        fontName="Helvetica-Bold", alignment=TA_LEFT
    )
    # Estilos para el estado de Habeas Data (verde = aceptado, rojo = pendiente)
    estilo_hd_ok = ParagraphStyle(
        "hd_ok", fontSize=7.5, leading=9.5,
        textColor=VERDE_OK, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    estilo_hd_no = ParagraphStyle(
        "hd_no", fontSize=7.5, leading=9.5,
        textColor=ALERTA_ROJO, fontName="Helvetica-Bold", alignment=TA_CENTER
    )

    # Columnas: Nombre, Edad, Estado, Teléfono, Correo, Talla, Peso, IMC, %Grasa, Evals, Habeas Data
    cab_pac = ["Nombre", "Edad", "Estado", "Teléfono", "Correo", "Talla (m)",
               "Peso (kg)", "IMC", "% Grasa", "Evals.", "Habeas Data"]
    proporciones = [0.18, 0.04, 0.07, 0.09, 0.15, 0.06, 0.06, 0.05, 0.06, 0.05, 0.08]
    anchos_pac_pdf = [ancho_total * p for p in proporciones]

    filas_pac = [[Paragraph(c, estilo_cab_tabla) for c in cab_pac]]
    for pac in datos["pacientes"]:
        tiene_alerta = pac.get("tiene_alerta", False)
        est_nombre   = estilo_alerta_txt if tiene_alerta else estilo_cel_tabla
        est_centro   = estilo_alerta_txt if tiene_alerta else estilo_cel_c
        hd_ok        = pac.get("habeas_data_aceptado", False)
        est_hd       = estilo_hd_ok if hd_ok else estilo_hd_no

        filas_pac.append([
            Paragraph(pac["nombre"],                            est_nombre),
            Paragraph(str(pac["edad"]),                         est_centro),
            Paragraph((pac["estado"] or "—").capitalize(),     est_centro),
            Paragraph(pac.get("telefono") or "—",               est_centro),
            Paragraph(pac.get("correo") or "—",                 est_centro),
            Paragraph(str(pac["talla_metros"]) if pac["talla_metros"] is not None else "—", est_centro),
            Paragraph(str(pac["peso_actual_kg"] or pac["peso_inicial_kg"] or "—"), est_centro),
            Paragraph(str(pac["imc"] or "—"),                  est_centro),
            Paragraph(str(pac["porcentaje_grasa"] or "—"),     est_centro),
            Paragraph(str(pac["total_evaluaciones"]),          est_centro),
            Paragraph("Sí" if hd_ok else "No",                  est_hd),
        ])

    tabla_pac = Table(filas_pac, colWidths=anchos_pac_pdf,
                      repeatRows=1)

    # Estilo alternado de filas
    estilo_tabla_pac = [
        ("BACKGROUND",    (0, 0), (-1, 0),  VERDE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  BLANCO),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CL]),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]

    # Resaltar filas con alerta en rojo claro (alerta real, no color de marca)
    for idx, pac in enumerate(datos["pacientes"], start=1):
        if pac.get("tiene_alerta"):
            estilo_tabla_pac.append(
                ("BACKGROUND", (0, idx), (-1, idx), ALERTA_MED)
            )

    tabla_pac.setStyle(TableStyle(estilo_tabla_pac))
    elementos.append(tabla_pac)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── ALERTAS ACTIVAS ───────────────────────────────────────────────────
    if datos["alertas"]:
        elementos.append(tabla_seccion(
            f"  ⚠  ALERTAS ACTIVAS — {len(datos['alertas'])} PACIENTE(S)"
        ))
        elementos.append(Spacer(1, 0.2 * cm))

        cab_alertas = ["Paciente", "Fecha", "Detalle de la Alerta"]
        anchos_alertas = [ancho_total * 0.22, ancho_total * 0.12,
                          ancho_total * 0.66]
        filas_alertas = [[Paragraph(c, estilo_cab_tabla) for c in cab_alertas]]

        for alerta in datos["alertas"]:
            filas_alertas.append([
                Paragraph(alerta["nombre"],  estilo_cel_tabla),
                Paragraph(alerta["fecha"],   estilo_cel_c),
                Paragraph(alerta["detalle"], ParagraphStyle(
                    "det", fontSize=7.5, leading=9.5,
                    textColor=colors.HexColor("#B71C1C"),
                    fontName="Helvetica"
                )),
            ])

        tabla_alertas = Table(filas_alertas, colWidths=anchos_alertas,
                              repeatRows=1)
        tabla_alertas.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  ALERTA_ROJO),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  BLANCO),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ALERTA_CL, ALERTA_MED]),
            ("GRID",          (0, 0), (-1, -1), 0.3, ALERTA_MED),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabla_alertas)
        elementos.append(Spacer(1, 0.5 * cm))

    # ── TOP 5 PACIENTES ───────────────────────────────────────────────────
    if datos["top_pacientes"]:
        elementos.append(tabla_seccion("  TOP 5 PACIENTES — MÁS EVALUACIONES"))
        elementos.append(Spacer(1, 0.2 * cm))

        max_top = max((p["total"] for p in datos["top_pacientes"]), default=1)
        anchos_top = [ancho_total * 0.06, ancho_total * 0.40,
                      ancho_total * 0.12, ancho_total * 0.42]

        filas_top = [[
            Paragraph(c, estilo_cab_tabla)
            for c in ["#", "Paciente", "Total", "Rendimiento"]
        ]]

        for rank, pac in enumerate(datos["top_pacientes"], start=1):
            barra_len = int((pac["total"] / max_top) * 25) if max_top > 0 else 0
            barra_txt = "●" * barra_len

            filas_top.append([
                Paragraph(str(rank),       estilo_cel_c),
                Paragraph(pac["nombre"],   estilo_cel_tabla),
                Paragraph(str(pac["total"]), estilo_cel_c),
                Paragraph(barra_txt, ParagraphStyle(
                    "barra", fontSize=8, leading=10,
                    textColor=VERDE, fontName="Helvetica",
                    alignment=TA_LEFT
                )),
            ])

        tabla_top = Table(filas_top, colWidths=anchos_top, repeatRows=1)
        tabla_top.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  VERDE_OSC),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  BLANCO),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CL]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabla_top)
        elementos.append(Spacer(1, 0.5 * cm))

    # ── EVOLUCIÓN MENSUAL ─────────────────────────────────────────────────
    if datos["evolucion"]:
        elementos.append(tabla_seccion(
            "  EVALUACIONES POR MES — ÚLTIMOS 12 MESES"
        ))
        elementos.append(Spacer(1, 0.2 * cm))

        max_ev = max((m["total"] for m in datos["evolucion"]), default=1)
        anchos_ev = [ancho_total * 0.15, ancho_total * 0.10,
                     ancho_total * 0.75]
        filas_ev = [[
            Paragraph(c, estilo_cab_tabla)
            for c in ["Período", "Total", "Actividad"]
        ]]

        for i, mes in enumerate(datos["evolucion"]):
            barra_len = int((mes["total"] / max_ev) * 40) if max_ev > 0 else 0
            barra_txt = "▌" * barra_len
            par = (i % 2 == 0)
            bg  = BLANCO if par else GRIS_CL

            filas_ev.append([
                Paragraph(mes["periodo"], estilo_cel_c),
                Paragraph(str(mes["total"]), estilo_cel_c),
                Paragraph(barra_txt, ParagraphStyle(
                    "barraev", fontSize=9, leading=11,
                    textColor=VERDE, fontName="Helvetica",
                    alignment=TA_LEFT
                )),
            ])

        tabla_ev = Table(filas_ev, colWidths=anchos_ev, repeatRows=1)
        tabla_ev.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  VERDE_OSC),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  BLANCO),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CL]),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabla_ev)
        elementos.append(Spacer(1, 0.5 * cm))

    # ── PIE DE PÁGINA ─────────────────────────────────────────────────────
    elementos.append(HRFlowable(
        width="100%", thickness=1.5,
        color=VERDE, spaceAfter=6
    ))
    elementos.append(Paragraph(
        f"FitPro — Sistema de Gestión Deportiva Profesional  |  "
        f"Reporte generado el {datos['generado_en']}  |  "
        f"Entrenador: {datos['entrenador']}  |  Documento confidencial",
        estilo_nota
    ))

    # ─── Construir y retornar el PDF ──────────────────────────────────────
    doc.build(elementos)
    buffer.seek(0)

    nombre_archivo = (
        f"fitpro_reporte_global_"
        f"{datos['generado_en'].replace('-', '')}.pdf"
    )

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={nombre_archivo}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# =============================================================
# ENDPOINT EXISTENTE: NETWORK INFO
# =============================================================

@router.get("/network-info")
async def obtener_info_red(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna la IP de red local del servidor anfitrión para el código QR.
    Prioridades: HOST_IP inyectada > socket UDP > hostname.
    """
    host_ip = os.getenv("HOST_IP", "").strip()

    def es_ip_red_valida(ip: str) -> bool:
        """Valida que sea una IPv4 accesible en red local (no loopback, no Docker)"""
        if not ip:
            return False
        segmentos_invalidos = ("127.", "172.", "169.254.", "0.")
        if ip in ["localhost", ""]:
            return False
        for seg in segmentos_invalidos:
            if ip.startswith(seg):
                return False
        partes = ip.split(".")
        if len(partes) != 4:
            return False
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in partes)

    # PRIORIDAD 1: IP inyectada por el script de lanzamiento
    if es_ip_red_valida(host_ip):
        logger.info(f"IP de red desde HOST_IP: {host_ip}")
        return {"ip": host_ip, "url": f"http://{host_ip}", "puerto": 80, "fuente": "host"}

    # PRIORIDAD 2: Socket UDP ficticio (solo útil fuera de Docker)
    ip_socket = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.connect(("8.8.8.8", 80))
        ip_socket = sock.getsockname()[0]
        sock.close()
    except Exception:
        pass

    if not ip_socket:
        try:
            ip_socket = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip_socket = "localhost"

    logger.warning(f"HOST_IP no disponible. IP detectada por socket: {ip_socket}")
    return {"ip": ip_socket, "url": f"http://{ip_socket}", "puerto": 80, "fuente": "socket"}