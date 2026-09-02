# backend/app/routers/evaluations.py
# Endpoints CRUD para evaluaciones físicas y exportación de reportes (Excel y PDF)

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import io
from datetime import date

from app.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.evaluation import Evaluation
from app.schemas import EvaluationCreate, EvaluationResponse
from app.utils.security import get_current_active_user
from app.utils.consent import tiene_consentimiento_valido
from app.utils.calculations import (
    calcular_imc, calcular_indice_ruffier,
    generar_alertas, comparar_evaluaciones,
    clasificar_ruffier, calcular_grasa_kg, calcular_masa_magra_kg,
    calcular_promedios_evaluaciones, generar_resumen_progreso,
    generar_analisis_completo
)

# -----------------------------------------------
# Configuración del router de evaluaciones
# -----------------------------------------------
router = APIRouter(prefix="/evaluations", tags=["Evaluaciones"])
logger = logging.getLogger(__name__)


@router.post("/patients/{patient_id}", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
async def crear_evaluacion(
    patient_id: int,
    eval_data: EvaluationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Registra una nueva evaluación física para un paciente.
    Calcula automáticamente IMC, Índice Ruffier y genera alertas.
    Requiere que el paciente tenga un consentimiento informado vigente y
    válido (módulo de Habeas Data); de lo contrario se bloquea con 403.
    """
    # Verificar que el paciente pertenece al entrenador
    paciente = _verificar_paciente(patient_id, current_user.id, db)

    # ── PUERTA DE HABEAS DATA ──────────────────────────────────────────
    # No se permite iniciar evaluaciones sin un consentimiento informado
    # completo y correspondiente a la versión vigente del documento.
    if not tiene_consentimiento_valido(db, patient_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El paciente debe completar el proceso de consentimiento informado "
                   "(Habeas Data) antes de iniciar evaluaciones."
        )

    # Calcular número de evaluación secuencial
    num_evaluacion = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).count() + 1

    # Preparar datos de la evaluación
    eval_dict = eval_data.model_dump(exclude_none=True)

    # Calcular IMC automáticamente si hay peso y talla
    peso = eval_dict.get("peso_kg") or paciente.peso_inicial_kg
    talla = eval_dict.get("talla_metros") or paciente.talla_metros
    imc_calculado = calcular_imc(peso, talla)

    # Calcular Índice de Ruffier si hay las tres frecuencias cardíacas
    indice_ruffier = None
    if all(k in eval_dict for k in ["fc_reposo", "fc_post_esfuerzo", "fc_minuto_recuperacion"]):
        indice_ruffier = calcular_indice_ruffier(
            eval_dict["fc_reposo"],
            eval_dict["fc_post_esfuerzo"],
            eval_dict["fc_minuto_recuperacion"]
        )

    # Generar alertas de salud automáticas
    eval_con_imc = {**eval_dict, "imc": imc_calculado}
    tiene_alerta, detalle_alerta = generar_alertas(eval_con_imc)

    # Crear el registro de evaluación
    nueva_evaluacion = Evaluation(
        patient_id=patient_id,
        trainer_id=current_user.id,
        numero_evaluacion=num_evaluacion,
        imc=imc_calculado,
        indice_ruffier=indice_ruffier,
        tiene_alerta=tiene_alerta,
        detalle_alerta=detalle_alerta,
        **eval_dict
    )

    db.add(nueva_evaluacion)
    db.commit()
    db.refresh(nueva_evaluacion)

    logger.info(f"Evaluación creada: {nueva_evaluacion.id} para paciente: {patient_id}")

    return nueva_evaluacion


@router.get("/patients/{patient_id}", response_model=List[EvaluationResponse])
async def listar_evaluaciones_paciente(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista todas las evaluaciones históricas de un paciente.
    Ordenadas cronológicamente ascendente para análisis de progreso.
    """
    # Verificar acceso al paciente
    _verificar_paciente(patient_id, current_user.id, db)

    evaluaciones = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).order_by(Evaluation.fecha_evaluacion.asc()).all()

    return evaluaciones


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
async def obtener_evaluacion(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtiene los datos completos de una evaluación específica.
    Verifica que pertenezca al entrenador autenticado.
    """
    evaluacion = _get_evaluation_or_404(evaluation_id, current_user.id, db)
    return evaluacion


@router.put("/{evaluation_id}", response_model=EvaluationResponse)
async def actualizar_evaluacion(
    evaluation_id: int,
    eval_data: EvaluationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Actualiza una evaluación existente y recalcula indicadores automáticos.
    Recalcula IMC, Ruffier y alertas con los nuevos datos.
    """
    evaluacion = _get_evaluation_or_404(evaluation_id, current_user.id, db)

    # Actualizar campos con los nuevos datos
    update_data = eval_data.model_dump(exclude_unset=True)
    for campo, valor in update_data.items():
        setattr(evaluacion, campo, valor)

    # Recalcular IMC con nuevos valores
    if evaluacion.peso_kg and evaluacion.talla_metros:
        evaluacion.imc = calcular_imc(evaluacion.peso_kg, evaluacion.talla_metros)

    # Recalcular Ruffier si están los datos
    if all([evaluacion.fc_reposo, evaluacion.fc_post_esfuerzo, evaluacion.fc_minuto_recuperacion]):
        evaluacion.indice_ruffier = calcular_indice_ruffier(
            evaluacion.fc_reposo, evaluacion.fc_post_esfuerzo, evaluacion.fc_minuto_recuperacion
        )

    # Regenerar alertas con datos actualizados
    eval_dict = {c.name: getattr(evaluacion, c.name) for c in evaluacion.__table__.columns}
    evaluacion.tiene_alerta, evaluacion.detalle_alerta = generar_alertas(eval_dict)

    db.commit()
    db.refresh(evaluacion)

    return evaluacion


@router.delete("/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_evaluacion(
    evaluation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Elimina permanentemente una evaluación.
    Operación destructiva - requiere confirmación en el frontend.
    """
    evaluacion = _get_evaluation_or_404(evaluation_id, current_user.id, db)

    db.delete(evaluacion)
    db.commit()

    logger.info(f"Evaluación eliminada: {evaluation_id}")


@router.get("/patients/{patient_id}/comparar")
async def comparar_evaluaciones_paciente(
    patient_id: int,
    eval_id_1: int,
    eval_id_2: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Compara dos evaluaciones del mismo paciente y retorna los deltas.
    Indica si cada indicador mejoró, empeoró o se mantuvo.
    """
    _verificar_paciente(patient_id, current_user.id, db)

    eval1 = db.query(Evaluation).filter(
        Evaluation.id == eval_id_1,
        Evaluation.patient_id == patient_id
    ).first()

    eval2 = db.query(Evaluation).filter(
        Evaluation.id == eval_id_2,
        Evaluation.patient_id == patient_id
    ).first()

    if not eval1 or not eval2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Una o ambas evaluaciones no encontradas"
        )

    def eval_to_dict(e):
        return {c.name: getattr(e, c.name) for c in e.__table__.columns}

    comparacion = comparar_evaluaciones(eval_to_dict(eval1), eval_to_dict(eval2))

    return {
        "evaluacion_anterior": EvaluationResponse.model_validate(eval1),
        "evaluacion_actual": EvaluationResponse.model_validate(eval2),
        "comparacion": comparacion
    }


@router.get("/patients/{patient_id}/export/excel")
async def exportar_excel(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Genera y descarga un archivo Excel con el historial completo del paciente.
    Incluye hoja de datos del paciente y hoja de evaluaciones.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from io import BytesIO
    import openpyxl.utils

    paciente = _verificar_paciente(patient_id, current_user.id, db)
    evaluaciones = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).order_by(Evaluation.fecha_evaluacion.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Evaluaciones"

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="CC0000", end_color="CC0000", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center")

    encabezados = [
        "Fecha", "Evaluación #", "Peso (kg)", "IMC", "% Grasa", "% Agua",
        "Músculo (kg)", "Oxigenación", "FC (lpm)", "TA", "Perímetro Abd.",
        "Índice Ruffier", "Fuerza Der. (kg)", "Test Wells (cm)",
        "Condición", "Alertas"
    ]

    for col, header in enumerate(encabezados, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    for row, eva in enumerate(evaluaciones, 2):
        ws.cell(row=row, column=1, value=str(eva.fecha_evaluacion))
        ws.cell(row=row, column=2, value=eva.numero_evaluacion)
        ws.cell(row=row, column=3, value=eva.peso_kg)
        ws.cell(row=row, column=4, value=eva.imc)
        ws.cell(row=row, column=5, value=eva.porcentaje_grasa)
        ws.cell(row=row, column=6, value=eva.porcentaje_agua)
        ws.cell(row=row, column=7, value=eva.musculo_kg)
        ws.cell(row=row, column=8, value=eva.oxigenacion_porcentaje)
        ws.cell(row=row, column=9, value=eva.frecuencia_cardiaca_rpm)
        ws.cell(row=row, column=10, value=f"{eva.tension_sistolica}/{eva.tension_diastolica}" if eva.tension_sistolica else "")
        ws.cell(row=row, column=11, value=eva.perimetro_abdominal_cm)
        ws.cell(row=row, column=12, value=eva.indice_ruffier)
        ws.cell(row=row, column=13, value=eva.fuerza_manual_der_kg)
        ws.cell(row=row, column=14, value=eva.test_wells_cm)
        ws.cell(row=row, column=15, value=eva.condicion_fisica.value if eva.condicion_fisica else "")
        ws.cell(row=row, column=16, value=eva.detalle_alerta or "Sin alertas")

    for col in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[openpyxl.utils.get_column_letter(col[0].column)].width = min(max_length + 4, 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nombre_archivo = f"fitpro_{paciente.nombre_completo.replace(' ', '_')}_{date.today()}.xlsx"

    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )


# =============================================================
# NUEVO ENDPOINT: EXPORTAR ANÁLISIS DEL PACIENTE EN PDF
# Reporte pensado para que el PACIENTE entienda sus resultados:
# cada indicador se muestra con una barra de rango saludable
# (según su género y edad) y un marcador de dónde cae su resultado,
# más un veredicto general y gráficas de evolución.
# =============================================================

@router.get("/patients/{patient_id}/export/pdf")
async def exportar_pdf(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Genera y descarga el reporte PDF de análisis del paciente:
      - Datos generales del paciente
      - Veredicto general del estado de salud (según % de indicadores en rango)
      - Ficha visual de cada indicador: valor actual + barra de rango saludable
        (grasa corporal, agua, masa ósea, perímetro abdominal, presión arterial,
        peso según talla, IMC) clasificado según género y edad
      - Gráficas de evolución de peso y % de grasa corporal
      - Comparación de progreso entre la primera y la última evaluación
      - Historial completo de evaluaciones y alertas activas
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.graphics.shapes import Drawing, Rect, Circle, String
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.widgets.markers import makeMarker

    paciente = _verificar_paciente(patient_id, current_user.id, db)
    evaluaciones_orm = db.query(Evaluation).filter(
        Evaluation.patient_id == patient_id
    ).order_by(Evaluation.fecha_evaluacion.asc()).all()

    evaluaciones = [
        {c.name: getattr(ev, c.name) for c in ev.__table__.columns}
        for ev in evaluaciones_orm
    ]

    genero = paciente.genero.value
    edad = paciente.edad
    talla = paciente.talla_metros

    promedios = calcular_promedios_evaluaciones(evaluaciones)
    resumen_progreso = generar_resumen_progreso(evaluaciones)
    ultima = evaluaciones[-1] if evaluaciones else None

    # Análisis visual completo de la última evaluación (indicadores + veredicto)
    analisis = generar_analisis_completo(ultima, genero, edad, talla) if ultima else \
        {"indicadores": [], "veredicto": {
            "estado": "Sin evaluaciones", "color": "gris",
            "mensaje": "Este paciente aún no tiene evaluaciones registradas.",
            "porcentaje_saludable": None, "indicadores_fuera_de_rango": []
        }}

    # -----------------------------------------------
    # Paleta de colores — estética médica verde/blanco
    # -----------------------------------------------
    VERDE_PRIMARIO = colors.HexColor("#16A34A")
    VERDE_OSCURO   = colors.HexColor("#15803D")
    VERDE_CLARO    = colors.HexColor("#E8F5E9")
    VERDE_SUAVE    = colors.HexColor("#86EFAC")
    GRIS_OSCURO    = colors.HexColor("#374E37")
    GRIS_CLARO     = colors.HexColor("#F4F8F4")
    GRIS_BARRA     = colors.HexColor("#E2EAE2")
    NEGRO_TEXTO    = colors.HexColor("#111827")
    BLANCO         = colors.white
    ROJO_ALERTA    = colors.HexColor("#EF4444")
    ROJO_CLARO     = colors.HexColor("#FEE2E2")
    AMARILLO_WARN  = colors.HexColor("#F59E0B")
    AMARILLO_CLARO = colors.HexColor("#FEF3C7")

    COLOR_POR_VEREDICTO = {"verde": VERDE_PRIMARIO, "amarillo": AMARILLO_WARN, "rojo": ROJO_ALERTA, "gris": GRIS_OSCURO}
    FONDO_POR_VEREDICTO = {"verde": VERDE_CLARO, "amarillo": AMARILLO_CLARO, "rojo": ROJO_CLARO, "gris": GRIS_CLARO}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"FitPro - Reporte {paciente.nombre_completo}",
        author=current_user.nombre_completo
    )

    # -----------------------------------------------
    # Estilos de texto reutilizables
    # -----------------------------------------------
    estilo_titulo = ParagraphStyle(
        "titulo", fontSize=20, leading=24, textColor=BLANCO,
        fontName="Helvetica-Bold", alignment=TA_LEFT, leftIndent=8
    )
    estilo_subtitulo = ParagraphStyle(
        "subtitulo", fontSize=9, leading=13, textColor=colors.HexColor("#E8F5E9"),
        fontName="Helvetica", alignment=TA_LEFT, leftIndent=8
    )
    estilo_seccion = ParagraphStyle(
        "seccion", fontSize=11, leading=15, textColor=BLANCO,
        fontName="Helvetica-Bold", alignment=TA_LEFT, leftIndent=6
    )
    estilo_celda = ParagraphStyle(
        "celda", fontSize=8, leading=10, textColor=NEGRO_TEXTO, fontName="Helvetica"
    )
    estilo_celda_c = ParagraphStyle(
        "celda_c", fontSize=8, leading=10, textColor=NEGRO_TEXTO,
        fontName="Helvetica", alignment=TA_CENTER
    )
    estilo_cab_tabla = ParagraphStyle(
        "cab_tabla", fontSize=8, leading=10, textColor=BLANCO,
        fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    estilo_nota = ParagraphStyle(
        "nota", fontSize=7, leading=10, textColor=GRIS_OSCURO,
        fontName="Helvetica", alignment=TA_CENTER
    )

    elementos = []
    ancho_total = doc.width

    def barra_seccion(texto):
        """Barra de encabezado de sección con fondo verde oscuro"""
        t = Table([[Paragraph(texto, estilo_seccion)]], colWidths=[ancho_total])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), VERDE_OSCURO),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return t

    def crear_barra_rango(indicador, ancho=340, alto=34):
        """
        Dibuja la barra de rango saludable de un indicador: escala completa
        en gris, zona saludable resaltada en verde, y un marcador circular
        en la posición exacta del resultado del paciente (verde si está en
        rango saludable, rojo si está fuera).
        """
        d = Drawing(ancho, alto)
        escala_min, escala_max = indicador["escala_min"], indicador["escala_max"]
        zona_min, zona_max = indicador["zona_min"], indicador["zona_max"]
        valor = indicador["valor"]
        rango_total = escala_max - escala_min or 1

        def x_pos(v):
            v = max(escala_min, min(escala_max, v))
            return (v - escala_min) / rango_total * ancho

        barra_y, barra_h = 14, 10

        # Fondo de la escala completa
        d.add(Rect(0, barra_y, ancho, barra_h, fillColor=GRIS_BARRA, strokeColor=None, rx=3, ry=3))

        # Zona saludable resaltada
        zx0, zx1 = x_pos(max(zona_min, escala_min)), x_pos(min(zona_max, escala_max))
        if zx1 > zx0:
            d.add(Rect(zx0, barra_y, zx1 - zx0, barra_h, fillColor=VERDE_SUAVE, strokeColor=None, rx=3, ry=3))

        # Marcador del resultado del paciente
        if valor is not None:
            vx = x_pos(valor)
            color_marcador = VERDE_PRIMARIO if indicador["es_saludable"] else ROJO_ALERTA
            d.add(Circle(vx, barra_y + barra_h / 2, 6, fillColor=color_marcador, strokeColor=BLANCO, strokeWidth=1.3))
            texto_valor = f"{valor}{indicador['unidad']}"
            d.add(String(vx, barra_y + barra_h + 6, texto_valor, fontSize=8,
                          fontName="Helvetica-Bold", fillColor=color_marcador, textAnchor="middle"))

        return d

    def crear_grafica_evolucion(valores, categorias, titulo, color_hex):
        """Genera una gráfica de línea simple de la evolución de un indicador"""
        d = Drawing(240, 145)
        chart = HorizontalLineChart()
        chart.x, chart.y = 32, 22
        chart.width, chart.height = 195, 95
        chart.data = [valores]
        chart.categoryAxis.categoryNames = categorias
        chart.categoryAxis.labels.fontSize = 6
        chart.categoryAxis.labels.fillColor = GRIS_OSCURO
        margen = max((max(valores) - min(valores)) * 0.25, 1)
        chart.valueAxis.valueMin = round(min(valores) - margen, 1)
        chart.valueAxis.valueMax = round(max(valores) + margen, 1)
        chart.valueAxis.labels.fontSize = 6
        chart.valueAxis.labels.fillColor = GRIS_OSCURO
        chart.lines[0].strokeColor = colors.HexColor(color_hex)
        chart.lines[0].strokeWidth = 2.2
        chart.lines[0].symbol = makeMarker("Circle")
        d.add(chart)
        d.add(String(120, 134, titulo, fontSize=8.5, fontName="Helvetica-Bold",
                      fillColor=NEGRO_TEXTO, textAnchor="middle"))
        return d

    # ── ENCABEZADO PRINCIPAL ────────────────────────────────────────────
    tabla_titulo = Table(
        [[Paragraph("🩺 FITPRO", estilo_titulo),
          Paragraph("MI ANÁLISIS DE SALUD Y PROGRESO", estilo_titulo)]],
        colWidths=[ancho_total * 0.28, ancho_total * 0.72]
    )
    tabla_titulo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), VERDE_PRIMARIO),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_titulo)

    tabla_sub = Table(
        [[Paragraph(
            f"Paciente: {paciente.nombre_completo}  |  "
            f"Entrenador: {current_user.nombre_completo}  |  "
            f"Generado: {date.today()}",
            estilo_subtitulo
        )]],
        colWidths=[ancho_total]
    )
    tabla_sub.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_OSCURO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabla_sub)
    elementos.append(Spacer(1, 0.4 * cm))

    # ── VEREDICTO GENERAL ───────────────────────────────────────────────
    veredicto = analisis["veredicto"]
    color_ver = COLOR_POR_VEREDICTO.get(veredicto["color"], GRIS_OSCURO)
    fondo_ver = FONDO_POR_VEREDICTO.get(veredicto["color"], GRIS_CLARO)

    estilo_estado = ParagraphStyle(
        "estado_ver", fontSize=16, leading=20, textColor=color_ver,
        fontName="Helvetica-Bold", alignment=TA_LEFT
    )
    estilo_mensaje_ver = ParagraphStyle(
        "mensaje_ver", fontSize=9, leading=13, textColor=GRIS_OSCURO,
        fontName="Helvetica", alignment=TA_LEFT
    )

    porcentaje_txt = f"{veredicto['porcentaje_saludable']}% de sus indicadores están en rango saludable" \
        if veredicto["porcentaje_saludable"] is not None else ""

    celda_veredicto = [
        Paragraph(f"Estado general: {veredicto['estado']}", estilo_estado),
        Paragraph(veredicto["mensaje"], estilo_mensaje_ver),
    ]
    if porcentaje_txt:
        celda_veredicto.append(Paragraph(porcentaje_txt, estilo_mensaje_ver))

    tabla_veredicto = Table([[celda_veredicto]], colWidths=[ancho_total])
    tabla_veredicto.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fondo_ver),
        ("BOX", (0, 0), (-1, -1), 1.2, color_ver),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ]))
    elementos.append(tabla_veredicto)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── DATOS DEL PACIENTE ──────────────────────────────────────────────
    elementos.append(barra_seccion("  DATOS DEL PACIENTE"))
    elementos.append(Spacer(1, 0.2 * cm))

    filas_datos = [
        ["Nombre completo", paciente.nombre_completo, "Edad", f"{paciente.edad} años"],
        ["Género", paciente.genero.value.capitalize(), "Talla", f"{paciente.talla_metros} m"],
        ["Peso inicial", f"{paciente.peso_inicial_kg} kg", "Fecha de ingreso",
         str(paciente.fecha_ingreso) if paciente.fecha_ingreso else "No registrada"],
        ["Objetivos", paciente.objetivos or "No registrados", "Condición médica",
         paciente.condicion_medica or "Ninguna registrada"],
    ]

    filas_pdf = [
        [Paragraph(f"<b>{a}</b>", estilo_celda), Paragraph(str(b), estilo_celda),
         Paragraph(f"<b>{c}</b>", estilo_celda), Paragraph(str(d), estilo_celda)]
        for a, b, c, d in filas_datos
    ]

    tabla_datos = Table(
        filas_pdf,
        colWidths=[ancho_total * 0.18, ancho_total * 0.32, ancho_total * 0.18, ancho_total * 0.32]
    )
    tabla_datos.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
        ("BACKGROUND", (0, 0), (0, -1), VERDE_CLARO),
        ("BACKGROUND", (2, 0), (2, -1), VERDE_CLARO),
        ("BACKGROUND", (1, 0), (1, -1), BLANCO),
        ("BACKGROUND", (3, 0), (3, -1), BLANCO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_datos)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── FICHAS VISUALES DE INDICADORES CON BARRA DE RANGO ───────────────
    if ultima and analisis["indicadores"]:
        elementos.append(barra_seccion(
            f"  SUS RESULTADOS — Evaluación #{ultima.get('numero_evaluacion')} "
            f"del {ultima.get('fecha_evaluacion')} (rangos según su género y edad)"
        ))
        elementos.append(Spacer(1, 0.25 * cm))

        estilo_nombre_ind = ParagraphStyle(
            "nombre_ind", fontSize=9.5, leading=12, textColor=NEGRO_TEXTO,
            fontName="Helvetica-Bold"
        )
        estilo_clasif_ind = ParagraphStyle(
            "clasif_ind", fontSize=8.5, leading=11, fontName="Helvetica-Bold"
        )
        estilo_ref_ind = ParagraphStyle(
            "ref_ind", fontSize=7.5, leading=10, textColor=GRIS_OSCURO, fontName="Helvetica"
        )
        estilo_nota_extra = ParagraphStyle(
            "nota_extra_ind", fontSize=7.8, leading=10.5, textColor=VERDE_OSCURO,
            fontName="Helvetica-Oblique"
        )

        for ind in analisis["indicadores"]:
            color_estado = VERDE_PRIMARIO if ind["es_saludable"] else ROJO_ALERTA
            estilo_clasif_actual = ParagraphStyle(
                f"clasif_{ind['campo']}", parent=estilo_clasif_ind, textColor=color_estado
            )

            encabezado_ind = Table(
                [[Paragraph(ind["nombre"], estilo_nombre_ind),
                  Paragraph(ind["clasificacion"], estilo_clasif_actual)]],
                colWidths=[ancho_total * 0.6, ancho_total * 0.4]
            )
            encabezado_ind.setStyle(TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]))
            elementos.append(encabezado_ind)
            elementos.append(crear_barra_rango(ind, ancho=ancho_total))
            elementos.append(Paragraph(f"Rango saludable de referencia: {ind['texto_referencia']}", estilo_ref_ind))
            if ind.get("nota_extra"):
                elementos.append(Paragraph(f"ⓘ {ind['nota_extra']}", estilo_nota_extra))
            elementos.append(Spacer(1, 0.25 * cm))

        elementos.append(Spacer(1, 0.2 * cm))

    # ── GRÁFICAS DE EVOLUCIÓN (peso y % grasa) ──────────────────────────
    if len(evaluaciones) >= 2:
        elementos.append(barra_seccion("  EVOLUCIÓN A TRAVÉS DEL TIEMPO"))
        elementos.append(Spacer(1, 0.25 * cm))

        categorias = [f"Ev.{e.get('numero_evaluacion')}" for e in evaluaciones]
        pesos = [e.get("peso_kg") for e in evaluaciones]
        grasas = [e.get("porcentaje_grasa") for e in evaluaciones]

        graficas_disponibles = []
        if all(p is not None for p in pesos):
            graficas_disponibles.append(
                crear_grafica_evolucion(pesos, categorias, "Peso (kg)", "#16A34A")
            )
        if all(g is not None for g in grasas):
            graficas_disponibles.append(
                crear_grafica_evolucion(grasas, categorias, "% Grasa corporal", "#EF4444")
            )

        if graficas_disponibles:
            fila_graficas = Table([graficas_disponibles], colWidths=[ancho_total / len(graficas_disponibles)] * len(graficas_disponibles))
            fila_graficas.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))
            elementos.append(fila_graficas)
            elementos.append(Spacer(1, 0.5 * cm))

    # ── PROGRESO: PRIMERA VS ÚLTIMA EVALUACIÓN ──────────────────────────
    if resumen_progreso:
        elementos.append(barra_seccion(
            f"  PROGRESO GENERAL — Del {resumen_progreso['fecha_inicial']} "
            f"al {resumen_progreso['fecha_final']}"
        ))
        elementos.append(Spacer(1, 0.2 * cm))

        etiquetas_progreso = {
            "peso_kg": "Peso (kg)", "imc": "IMC", "porcentaje_grasa": "% Grasa",
            "musculo_kg": "Músculo (kg)", "indice_ruffier": "Índice Ruffier",
            "perimetro_abdominal_cm": "Perímetro abd. (cm)"
        }

        filas_prog = [[Paragraph(c, estilo_cab_tabla)
                       for c in ["Indicador", "Inicial", "Actual", "Cambio", "Evaluación"]]]

        for campo, etiqueta in etiquetas_progreso.items():
            dato = resumen_progreso["comparacion"].get(campo)
            if not dato:
                continue
            mejora = dato["mejoro"]
            texto_eval = "Mejoró" if mejora else ("Empeoró" if mejora is False else "Sin cambio")
            color_eval = VERDE_OSCURO if mejora else (ROJO_ALERTA if mejora is False else GRIS_OSCURO)
            estilo_eval = ParagraphStyle(
                f"eval_{campo}", fontSize=8, leading=10, fontName="Helvetica-Bold",
                textColor=color_eval, alignment=TA_CENTER
            )
            filas_prog.append([
                Paragraph(etiqueta, estilo_celda),
                Paragraph(str(dato["anterior"]), estilo_celda_c),
                Paragraph(str(dato["actual"]), estilo_celda_c),
                Paragraph(f"{'+' if dato['delta'] > 0 else ''}{dato['delta']}", estilo_celda_c),
                Paragraph(texto_eval, estilo_eval),
            ])

        tabla_prog = Table(
            filas_prog,
            colWidths=[ancho_total * 0.28, ancho_total * 0.16, ancho_total * 0.16,
                       ancho_total * 0.16, ancho_total * 0.24]
        )
        tabla_prog.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), VERDE_PRIMARIO),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CLARO]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabla_prog)
        elementos.append(Spacer(1, 0.5 * cm))

    # ── PROMEDIOS HISTÓRICOS ─────────────────────────────────────────────
    elementos.append(barra_seccion("  PROMEDIOS HISTÓRICOS DE TODAS LAS EVALUACIONES"))
    elementos.append(Spacer(1, 0.2 * cm))

    etiquetas_promedios = [
        ("peso_kg", "Peso (kg)"), ("imc", "IMC"),
        ("porcentaje_grasa", "% Grasa"), ("porcentaje_agua", "% Agua"),
        ("musculo_kg", "Músculo (kg)"), ("oxigenacion_porcentaje", "Oxigenación (%)"),
        ("frecuencia_cardiaca_rpm", "FC (lpm)"), ("perimetro_abdominal_cm", "Perímetro abd. (cm)"),
        ("indice_ruffier", "Índice Ruffier"), ("test_wells_cm", "Test Wells (cm)"),
    ]

    filas_prom = [[Paragraph(c, estilo_cab_tabla) for c in ["Indicador", "Promedio histórico"]]]
    for campo, etiqueta in etiquetas_promedios:
        valor = promedios.get(campo)
        filas_prom.append([
            Paragraph(etiqueta, estilo_celda),
            Paragraph(str(valor) if valor is not None else "Sin datos suficientes", estilo_celda_c)
        ])

    tabla_prom = Table(filas_prom, colWidths=[ancho_total * 0.6, ancho_total * 0.4])
    tabla_prom.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE_PRIMARIO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CLARO]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_prom)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── HISTORIAL COMPLETO DE EVALUACIONES ──────────────────────────────
    elementos.append(barra_seccion("  HISTORIAL COMPLETO DE EVALUACIONES"))
    elementos.append(Spacer(1, 0.2 * cm))

    cab_hist = ["#", "Fecha", "Peso", "IMC", "% Grasa", "Músculo", "FC", "Ruffier", "Alertas"]
    filas_hist = [[Paragraph(c, estilo_cab_tabla) for c in cab_hist]]

    for ev in evaluaciones:
        tiene_alerta = ev.get("tiene_alerta")
        estilo_fila = ParagraphStyle(
            "fila_alerta", fontSize=7.5, leading=9.5, fontName="Helvetica",
            textColor=ROJO_ALERTA if tiene_alerta else NEGRO_TEXTO, alignment=TA_CENTER
        )
        filas_hist.append([
            Paragraph(str(ev.get("numero_evaluacion")), estilo_fila),
            Paragraph(str(ev.get("fecha_evaluacion")), estilo_fila),
            Paragraph(str(ev.get("peso_kg") or "—"), estilo_fila),
            Paragraph(str(ev.get("imc") or "—"), estilo_fila),
            Paragraph(str(ev.get("porcentaje_grasa") or "—"), estilo_fila),
            Paragraph(str(ev.get("musculo_kg") or "—"), estilo_fila),
            Paragraph(str(ev.get("frecuencia_cardiaca_rpm") or "—"), estilo_fila),
            Paragraph(str(ev.get("indice_ruffier") or "—"), estilo_fila),
            Paragraph("⚠ Sí" if tiene_alerta else "✓ OK", estilo_fila),
        ])

    tabla_hist = Table(
        filas_hist,
        colWidths=[ancho_total * w for w in [0.06, 0.14, 0.11, 0.09, 0.11, 0.12, 0.10, 0.11, 0.16]],
        repeatRows=1
    )
    estilo_tabla_hist = [
        ("BACKGROUND", (0, 0), (-1, 0), VERDE_PRIMARIO),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E0E0E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CLARO]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, ev in enumerate(evaluaciones, start=1):
        if ev.get("tiene_alerta"):
            estilo_tabla_hist.append(("BACKGROUND", (0, i), (-1, i), ROJO_CLARO))
    tabla_hist.setStyle(TableStyle(estilo_tabla_hist))
    elementos.append(tabla_hist)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── ALERTAS ACTIVAS ─────────────────────────────────────────────────
    alertas_activas = [ev for ev in evaluaciones if ev.get("tiene_alerta")]
    if alertas_activas:
        elementos.append(barra_seccion(f"  ⚠ ALERTAS ACTIVAS — {len(alertas_activas)} EVALUACIÓN(ES)"))
        elementos.append(Spacer(1, 0.2 * cm))

        filas_alertas = [[Paragraph(c, estilo_cab_tabla) for c in ["Fecha", "Detalle de la alerta"]]]
        estilo_detalle = ParagraphStyle(
            "detalle_alerta", fontSize=8, leading=10, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#991B1B")
        )
        for ev in alertas_activas:
            filas_alertas.append([
                Paragraph(str(ev.get("fecha_evaluacion")), estilo_celda_c),
                Paragraph(ev.get("detalle_alerta") or "Sin detalle", estilo_detalle)
            ])

        tabla_alertas = Table(filas_alertas, colWidths=[ancho_total * 0.2, ancho_total * 0.8], repeatRows=1)
        tabla_alertas.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ROJO_ALERTA),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#FCA5A5")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ROJO_CLARO, colors.HexColor("#FEF2F2")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabla_alertas)
        elementos.append(Spacer(1, 0.5 * cm))

    # ── PIE DE PÁGINA ────────────────────────────────────────────────────
    elementos.append(HRFlowable(width="100%", thickness=1.2, color=VERDE_PRIMARIO, spaceAfter=6))
    elementos.append(Paragraph(
        f"FitPro — Sistema de Gestión de Salud y Seguimiento Físico  |  "
        f"Reporte generado el {date.today()}  |  "
        f"Los rangos de referencia son orientativos y no reemplazan una valoración médica profesional.",
        estilo_nota
    ))

    doc.build(elementos)
    buffer.seek(0)

    nombre_archivo = f"fitpro_analisis_{paciente.nombre_completo.replace(' ', '_')}_{date.today()}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={nombre_archivo}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


def _verificar_paciente(patient_id: int, trainer_id: int, db: Session) -> Patient:
    """Verifica que el paciente existe y pertenece al entrenador"""
    paciente = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.trainer_id == trainer_id,
        Patient.is_active == True
    ).first()

    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente no encontrado o sin acceso"
        )
    return paciente


def _get_evaluation_or_404(eval_id: int, trainer_id: int, db: Session) -> Evaluation:
    """Verifica que la evaluación existe y pertenece al entrenador"""
    evaluacion = db.query(Evaluation).filter(
        Evaluation.id == eval_id,
        Evaluation.trainer_id == trainer_id
    ).first()

    if not evaluacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluación no encontrada"
        )
    return evaluacion