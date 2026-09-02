# backend/app/routers/consent.py
# Endpoints del módulo de Habeas Data: documento vigente, estado de
# consentimiento de un paciente, registro de evidencia (firma + validación
# de identidad), historial inmutable, exportación de evidencia en PDF
# (para responder ante reclamos del paciente) y respaldo local de la base
# de datos.

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List
import shutil
import os
import io
import base64
import logging

from app.database import get_db
from app.config import settings
from app.models.user import User, UserRole
from app.models.patient import Patient
from app.models.consent import PatientConsent, ConsentDocumentVersion
from app.models.audit import AuditLog
from app.schemas.consent import (
    DocumentoVigenteResponse, ConsentEstadoResponse, ConsentCreate,
    ConsentResponse, ConsentHistorialItem, ConsentEvidenciaDetalle
)
from app.utils.security import get_current_active_user, require_roles
from app.utils.consent import (
    obtener_documento_vigente, tiene_consentimiento_valido,
    generar_hash_evidencia, hash_sha256, timestamp_iso
)

# -----------------------------------------------
# Configuración del router de consentimientos
# -----------------------------------------------
router = APIRouter(prefix="/consent", tags=["Habeas Data y Consentimiento"])
logger = logging.getLogger(__name__)


# -----------------------------------------------
# Función auxiliar: registrar entrada de auditoría (INSERT-only)
# -----------------------------------------------
def _registrar_auditoria(
    db: Session, usuario_id: int, accion: str, request: Request,
    patient_id: int = None, entidad_tipo: str = None,
    entidad_id: int = None, detalles: str = None
) -> None:
    """Crea un registro de auditoría para una acción sensible del sistema"""
    entrada = AuditLog(
        usuario_id=usuario_id,
        patient_id=patient_id,
        accion=accion,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        detalles=detalles,
        ip_origen=request.client.host if request.client else None
    )
    db.add(entrada)
    db.commit()


def _verificar_paciente(patient_id: int, trainer_id: int, db: Session) -> Patient:
    """Verifica que el paciente exista y pertenezca al entrenador autenticado"""
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


def _verificar_acceso_evidencia(consent_id: int, current_user: User, db: Session) -> PatientConsent:
    """
    Obtiene una evidencia de consentimiento y valida que el usuario actual
    tenga permiso para verla: administradores ven cualquiera, un entrenador
    solo las de sus propios pacientes.
    """
    consentimiento = db.query(PatientConsent).filter(PatientConsent.id == consent_id).first()

    if not consentimiento:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidencia no encontrada")

    if current_user.role != UserRole.ADMIN and consentimiento.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permisos para ver esta evidencia")

    return consentimiento


# -----------------------------------------------
# GET: documento de consentimiento vigente
# -----------------------------------------------
@router.get("/documento-vigente", response_model=DocumentoVigenteResponse)
async def obtener_documento(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna el documento de Habeas Data / consentimiento informado
    actualmente vigente, para mostrarlo al paciente antes de las evaluaciones.
    """
    documento = obtener_documento_vigente(db)
    if not documento:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No hay un documento de consentimiento configurado en el sistema"
        )
    return documento


# -----------------------------------------------
# GET: estado del consentimiento de un paciente
# -----------------------------------------------
@router.get("/patients/{patient_id}/estado", response_model=ConsentEstadoResponse)
async def obtener_estado_consentimiento(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Indica si el paciente puede iniciar evaluaciones. La usa el frontend para
    decidir si mostrar la pantalla de consentimiento, y el backend para
    validar el requisito antes de crear una evaluación.
    """
    paciente = _verificar_paciente(patient_id, current_user.id, db)

    documento_vigente = obtener_documento_vigente(db)
    ultimo = db.query(PatientConsent).filter(
        PatientConsent.patient_id == patient_id
    ).order_by(PatientConsent.created_at.desc()).first()

    valido = tiene_consentimiento_valido(db, patient_id)

    return ConsentEstadoResponse(
        tiene_consentimiento_valido=valido,
        version_vigente=documento_vigente.version if documento_vigente else None,
        version_firmada=ultimo.version_documento if ultimo else None,
        fecha_firma=ultimo.created_at if ultimo else None,
        requiere_actualizacion=bool(
            ultimo and documento_vigente and ultimo.version_documento != documento_vigente.version
        ),
        numero_documento_registrado=bool(paciente.numero_documento)
    )


# -----------------------------------------------
# POST: registrar el consentimiento (genera la evidencia)
# -----------------------------------------------
@router.post("/patients/{patient_id}", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def registrar_consentimiento(
    patient_id: int,
    datos: ConsentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.TRAINER]))
):
    """
    Registra la evidencia completa del proceso presencial de Habeas Data y
    consentimiento informado: aceptaciones del paciente, confirmación del
    profesional, firma en pantalla y validación de identidad por últimos
    4 dígitos del documento. Genera un hash de integridad sobre la evidencia.

    Endpoint INSERT-only: no existe forma de editar ni eliminar el registro
    generado, para proteger la integridad del historial.
    """
    paciente = _verificar_paciente(patient_id, current_user.id, db)

    # El paciente debe tener su número de documento registrado para validar su identidad
    if not paciente.numero_documento:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El paciente no tiene número de documento registrado. Regístrelo antes de continuar."
        )

    # Validar que TODAS las aceptaciones obligatorias sean verdaderas
    campos_obligatorios = [
        datos.acepta_datos_personales, datos.acepta_datos_sensibles,
        datos.acepta_consentimiento_informado, datos.profesional_confirma,
        datos.confirmacion_final
    ]
    if not all(campos_obligatorios):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Debe aceptar todas las autorizaciones y confirmaciones para continuar"
        )

    # Validar identidad: los últimos 4 dígitos deben coincidir con el documento registrado
    ultimos_4_reales = paciente.numero_documento.strip()[-4:]
    identidad_validada = (datos.ultimos_4_digitos == ultimos_4_reales)

    if not identidad_validada:
        # Se audita el intento fallido de validación de identidad
        _registrar_auditoria(
            db, current_user.id, "CONSENT_IDENTITY_MISMATCH", request,
            patient_id=patient_id, entidad_tipo="patient",
            detalles="Los últimos 4 dígitos ingresados no coinciden con el documento registrado"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los últimos 4 dígitos no coinciden con el documento del paciente"
        )

    documento_vigente = obtener_documento_vigente(db)
    if not documento_vigente:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No hay un documento de consentimiento configurado en el sistema"
        )

    # Hash independiente de la firma, para verificar su integridad por separado
    firma_hash = hash_sha256(datos.firma_base64)
    momento = timestamp_iso()

    # Hash de integridad de toda la evidencia (cualquier alteración de un
    # campo, incluida la firma, cambia este hash)
    hash_evidencia = generar_hash_evidencia({
        "patient_id": patient_id,
        "trainer_id": current_user.id,
        "profesional_id": current_user.id,
        "document_version_id": documento_vigente.id,
        "version_documento": documento_vigente.version,
        "acepta_datos_personales": datos.acepta_datos_personales,
        "acepta_datos_sensibles": datos.acepta_datos_sensibles,
        "acepta_consentimiento_informado": datos.acepta_consentimiento_informado,
        "profesional_confirma": datos.profesional_confirma,
        "confirmacion_final": datos.confirmacion_final,
        "ultimos_4_digitos": datos.ultimos_4_digitos,
        "identidad_validada": identidad_validada,
        "firma_hash": firma_hash,
        "momento": momento
    })

    nuevo_consentimiento = PatientConsent(
        patient_id=patient_id,
        trainer_id=current_user.id,
        profesional_id=current_user.id,
        document_version_id=documento_vigente.id,
        version_documento=documento_vigente.version,
        acepta_datos_personales=datos.acepta_datos_personales,
        acepta_datos_sensibles=datos.acepta_datos_sensibles,
        acepta_consentimiento_informado=datos.acepta_consentimiento_informado,
        profesional_confirma=datos.profesional_confirma,
        firma_base64=datos.firma_base64,
        firma_hash=firma_hash,
        ultimos_4_digitos=datos.ultimos_4_digitos,
        identidad_validada=identidad_validada,
        confirmacion_final=datos.confirmacion_final,
        hash_evidencia=hash_evidencia,
        ip_origen=request.client.host if request.client else None
    )

    db.add(nuevo_consentimiento)
    db.commit()
    db.refresh(nuevo_consentimiento)

    _registrar_auditoria(
        db, current_user.id, "CONSENT_CREATED", request,
        patient_id=patient_id, entidad_tipo="patient_consent",
        entidad_id=nuevo_consentimiento.id,
        detalles=f"Consentimiento versión {documento_vigente.version} registrado exitosamente"
    )

    logger.info(f"Consentimiento registrado: paciente={patient_id}, profesional={current_user.id}")

    return nuevo_consentimiento


# -----------------------------------------------
# GET: historial de consentimientos de un paciente
# -----------------------------------------------
@router.get("/patients/{patient_id}/historial", response_model=List[ConsentHistorialItem])
async def obtener_historial(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.TRAINER]))
):
    """
    Lista el historial completo e inmutable de consentimientos de un paciente,
    sin exponer la imagen de la firma (acceso restringido a roles autorizados).
    """
    _verificar_paciente(patient_id, current_user.id, db)

    consentimientos = db.query(PatientConsent).filter(
        PatientConsent.patient_id == patient_id
    ).order_by(PatientConsent.created_at.desc()).all()

    resultado = []
    for c in consentimientos:
        item = ConsentHistorialItem.model_validate(c)
        item.nombre_profesional = current_user.nombre_completo if c.profesional_id == current_user.id else None
        resultado.append(item)

    return resultado


# -----------------------------------------------
# GET: detalle completo de una evidencia (incluye firma)
# -----------------------------------------------
@router.get("/evidencia/{consent_id}", response_model=ConsentEvidenciaDetalle)
async def obtener_evidencia_detalle(
    consent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.TRAINER]))
):
    """
    Retorna el detalle completo de una evidencia de consentimiento, incluida
    la imagen de la firma. Es información sensible: el acceso queda
    registrado en la auditoría y solo está disponible para administradores
    y el entrenador dueño del paciente.
    """
    consentimiento = _verificar_acceso_evidencia(consent_id, current_user, db)

    profesional = db.query(User).filter(User.id == consentimiento.profesional_id).first()

    _registrar_auditoria(
        db, current_user.id, "CONSENT_EVIDENCE_VIEWED", request,
        patient_id=consentimiento.patient_id, entidad_tipo="patient_consent",
        entidad_id=consentimiento.id
    )

    respuesta = ConsentEvidenciaDetalle.model_validate(consentimiento)
    respuesta.nombre_profesional = profesional.nombre_completo if profesional else None
    return respuesta


# =============================================================
# NUEVO ENDPOINT: EXPORTAR LA EVIDENCIA DE CONSENTIMIENTO EN PDF
# Documento pensado para RESPONDER ANTE UN RECLAMO DEL PACIENTE:
# demuestra qué autorizó, que el profesional confirmó el proceso,
# la firma capturada en pantalla, la validación de identidad y el
# hash de integridad (para probar que el registro no fue alterado
# después de firmado).
# =============================================================

@router.get("/evidencia/{consent_id}/pdf")
async def exportar_evidencia_pdf(
    consent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.TRAINER]))
):
    """
    Genera y descarga el PDF de evidencia legal de un consentimiento ya
    registrado. Incluye:
      - Datos del paciente y del documento exacto que aceptó (versión)
      - Cada autorización otorgada, marcada como aceptada
      - Confirmación del profesional que gestionó el proceso presencial
      - Resultado de la validación de identidad (últimos 4 dígitos)
      - Imagen de la firma capturada en pantalla
      - Hash de integridad de la evidencia (SHA-256) e IP de origen

    Acceso restringido a administradores o al entrenador dueño del
    paciente. Cada descarga queda registrada en la auditoría, igual que
    la consulta del detalle en pantalla.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.utils import ImageReader

    # --- Verificación de acceso y carga de datos relacionados ---
    consentimiento = _verificar_acceso_evidencia(consent_id, current_user, db)

    paciente = db.query(Patient).filter(Patient.id == consentimiento.patient_id).first()
    if not paciente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente asociado no encontrado")

    documento_version = db.query(ConsentDocumentVersion).filter(
        ConsentDocumentVersion.id == consentimiento.document_version_id
    ).first()

    profesional = db.query(User).filter(User.id == consentimiento.profesional_id).first()
    nombre_profesional = profesional.nombre_completo if profesional else "No disponible"
    correo_profesional = profesional.email if profesional else "No disponible"

    # -----------------------------------------------
    # Paleta de colores — estética médica verde/blanco (igual al resto de PDFs)
    # -----------------------------------------------
    VERDE_PRIMARIO = colors.HexColor("#16A34A")
    VERDE_OSCURO   = colors.HexColor("#15803D")
    VERDE_CLARO    = colors.HexColor("#E8F5E9")
    GRIS_OSCURO    = colors.HexColor("#374E37")
    GRIS_CLARO     = colors.HexColor("#F4F8F4")
    NEGRO_TEXTO    = colors.HexColor("#111827")
    BLANCO         = colors.white
    ROJO_ALERTA    = colors.HexColor("#EF4444")
    ROJO_CLARO     = colors.HexColor("#FEE2E2")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"FitPro - Evidencia de Consentimiento {paciente.nombre_completo}",
        author=nombre_profesional
    )

    # -----------------------------------------------
    # Estilos de texto reutilizables
    # -----------------------------------------------
    estilo_titulo = ParagraphStyle(
        "titulo", fontSize=17, leading=21, textColor=BLANCO,
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
        "celda", fontSize=8.5, leading=11, textColor=NEGRO_TEXTO, fontName="Helvetica"
    )
    estilo_celda_valor = ParagraphStyle(
        "celda_valor", fontSize=8.5, leading=11, textColor=NEGRO_TEXTO, fontName="Helvetica-Bold"
    )
    estilo_ok = ParagraphStyle(
        "ok", fontSize=8.5, leading=11, textColor=VERDE_OSCURO,
        fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    estilo_no = ParagraphStyle(
        "no", fontSize=8.5, leading=11, textColor=ROJO_ALERTA,
        fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    estilo_nota = ParagraphStyle(
        "nota", fontSize=7, leading=10, textColor=GRIS_OSCURO,
        fontName="Helvetica", alignment=TA_CENTER
    )
    estilo_texto_legal = ParagraphStyle(
        "texto_legal", fontSize=7.6, leading=10.5, textColor=GRIS_OSCURO,
        fontName="Helvetica", alignment=TA_LEFT
    )
    estilo_hash = ParagraphStyle(
        "hash", fontSize=7.5, leading=10, textColor=NEGRO_TEXTO, fontName="Courier"
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

    def fila_dato(etiqueta, valor):
        """Fila de dos columnas: etiqueta gris + valor en negrita"""
        return [Paragraph(etiqueta, estilo_celda), Paragraph(str(valor), estilo_celda_valor)]

    # ── ENCABEZADO PRINCIPAL ────────────────────────────────────────────
    tabla_titulo = Table(
        [[Paragraph("🩺 FITPRO", estilo_titulo),
          Paragraph("EVIDENCIA DE CONSENTIMIENTO Y HABEAS DATA", estilo_titulo)]],
        colWidths=[ancho_total * 0.28, ancho_total * 0.72]
    )
    tabla_titulo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), VERDE_PRIMARIO),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_titulo)

    tabla_sub = Table(
        [[Paragraph(
            f"Registro N.° {consentimiento.id}  |  "
            f"Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC  |  "
            f"Solicitado por: {current_user.nombre_completo}",
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

    # ── AVISO LEGAL ──────────────────────────────────────────────────────
    aviso_legal = (
        "Este documento certifica que el paciente identificado a continuación "
        "otorgó, de forma presencial y verificable, su autorización para el "
        "tratamiento de datos personales y sensibles de salud, así como su "
        "consentimiento informado para las evaluaciones físicas realizadas "
        "por FitPro. La evidencia fue capturada digitalmente e incluye la "
        "firma del paciente, la validación de su identidad y un código de "
        "integridad (hash) que permite verificar que el registro no ha sido "
        "modificado desde su creación."
    )
    tabla_aviso = Table([[Paragraph(aviso_legal, estilo_texto_legal)]], colWidths=[ancho_total])
    tabla_aviso.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), VERDE_CLARO),
        ("BOX", (0, 0), (-1, -1), 1, VERDE_PRIMARIO),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    elementos.append(tabla_aviso)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── DATOS DEL PACIENTE Y DEL DOCUMENTO ACEPTADO ─────────────────────
    elementos.append(barra_seccion("  DATOS DEL PACIENTE Y DEL DOCUMENTO ACEPTADO"))
    elementos.append(Spacer(1, 0.2 * cm))

    fecha_firma_txt = consentimiento.created_at.strftime("%Y-%m-%d %H:%M:%S") + " UTC"

    filas_datos = [
        fila_dato("Nombre completo del paciente", paciente.nombre_completo),
        fila_dato("Número de documento", paciente.numero_documento or "No registrado"),
        fila_dato("Edad", f"{paciente.edad} años"),
        fila_dato("Género", paciente.genero.value.capitalize()),
        fila_dato("Versión del documento aceptado", consentimiento.version_documento),
        fila_dato("Título del documento", documento_version.titulo if documento_version else "No disponible"),
        fila_dato("Fecha y hora de la firma", fecha_firma_txt),
        fila_dato("Profesional que gestionó el proceso", f"{nombre_profesional} ({correo_profesional})"),
    ]

    tabla_datos = Table(filas_datos, colWidths=[ancho_total * 0.4, ancho_total * 0.6])
    tabla_datos.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
        ("BACKGROUND", (0, 0), (0, -1), VERDE_CLARO),
        ("BACKGROUND", (1, 0), (1, -1), BLANCO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_datos)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── AUTORIZACIONES OTORGADAS ────────────────────────────────────────
    elementos.append(barra_seccion("  AUTORIZACIONES OTORGADAS POR EL PACIENTE"))
    elementos.append(Spacer(1, 0.2 * cm))

    autorizaciones = [
        ("Tratamiento de datos personales",
         "Autoriza el tratamiento de nombre, contacto y datos demográficos.",
         consentimiento.acepta_datos_personales),
        ("Tratamiento de datos sensibles de salud",
         "Autoriza el tratamiento de sus evaluaciones físicas y de condición física.",
         consentimiento.acepta_datos_sensibles),
        ("Consentimiento informado",
         "Confirma haber recibido explicación sobre el propósito y las condiciones de las evaluaciones.",
         consentimiento.acepta_consentimiento_informado),
        ("Confirmación del profesional",
         "El profesional confirma haber explicado la información y resuelto las dudas del paciente.",
         consentimiento.profesional_confirma),
        ("Confirmación final del paciente",
         "El paciente declara haber leído, comprendido y aceptado todo lo anterior.",
         consentimiento.confirmacion_final),
    ]

    filas_auth = [[Paragraph(c, estilo_celda_valor) for c in ["Autorización", "Descripción", "Estado"]]]
    for titulo, descripcion, otorgada in autorizaciones:
        estado_par = Paragraph("✓ Aceptado", estilo_ok) if otorgada else Paragraph("✗ No aceptado", estilo_no)
        filas_auth.append([
            Paragraph(f"<b>{titulo}</b>", estilo_celda),
            Paragraph(descripcion, estilo_celda),
            estado_par
        ])

    tabla_auth = Table(
        filas_auth,
        colWidths=[ancho_total * 0.26, ancho_total * 0.54, ancho_total * 0.20],
        repeatRows=1
    )
    tabla_auth.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE_PRIMARIO),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLANCO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CLARO]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_auth)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── VALIDACIÓN DE IDENTIDAD ─────────────────────────────────────────
    elementos.append(barra_seccion("  VALIDACIÓN DE IDENTIDAD"))
    elementos.append(Spacer(1, 0.2 * cm))

    resultado_identidad = "✓ Coincide con el documento registrado" if consentimiento.identidad_validada \
        else "✗ No coincidía con el documento registrado"
    estilo_resultado = estilo_ok if consentimiento.identidad_validada else estilo_no

    filas_identidad = [
        fila_dato("Últimos 4 dígitos ingresados por el paciente", consentimiento.ultimos_4_digitos),
        [Paragraph("Resultado de la validación", estilo_celda), Paragraph(resultado_identidad, estilo_resultado)],
        fila_dato("IP de origen del registro", consentimiento.ip_origen or "No disponible"),
    ]
    tabla_identidad = Table(filas_identidad, colWidths=[ancho_total * 0.4, ancho_total * 0.6])
    tabla_identidad.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
        ("BACKGROUND", (0, 0), (0, -1), VERDE_CLARO),
        ("BACKGROUND", (1, 0), (1, -1), BLANCO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_identidad)
    elementos.append(Spacer(1, 0.5 * cm))

    # ── FIRMA DEL PACIENTE ───────────────────────────────────────────────
    elementos.append(barra_seccion("  FIRMA DEL PACIENTE"))
    elementos.append(Spacer(1, 0.25 * cm))

    try:
        _, datos_codificados = consentimiento.firma_base64.split(",", 1)
        bytes_imagen = base64.b64decode(datos_codificados)
        buffer_imagen = io.BytesIO(bytes_imagen)

        lector_imagen = ImageReader(buffer_imagen)
        ancho_original, alto_original = lector_imagen.getSize()
        ancho_firma = 11 * cm
        alto_firma = ancho_firma * (alto_original / ancho_original) if ancho_original else 3.5 * cm

        buffer_imagen.seek(0)
        imagen_firma = Image(buffer_imagen, width=ancho_firma, height=alto_firma)

        caja_firma = Table([[imagen_firma]], colWidths=[ancho_total])
        caja_firma.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BLANCO),
            ("BOX", (0, 0), (-1, -1), 1, VERDE_PRIMARIO),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        elementos.append(caja_firma)
    except Exception as e:
        logger.warning(f"No se pudo renderizar la firma del consentimiento {consentimiento.id}: {e}")
        elementos.append(Paragraph("No fue posible mostrar la imagen de la firma.", estilo_no))

    elementos.append(Spacer(1, 0.5 * cm))

    # ── INTEGRIDAD DE LA EVIDENCIA ──────────────────────────────────────
    elementos.append(barra_seccion("  INTEGRIDAD DE LA EVIDENCIA"))
    elementos.append(Spacer(1, 0.2 * cm))

    filas_integridad = [
        [Paragraph("Hash de integridad de la evidencia (SHA-256)", estilo_celda),
         Paragraph(consentimiento.hash_evidencia, estilo_hash)],
        [Paragraph("Hash de la firma (SHA-256)", estilo_celda),
         Paragraph(consentimiento.firma_hash, estilo_hash)],
    ]
    tabla_integridad = Table(filas_integridad, colWidths=[ancho_total * 0.4, ancho_total * 0.6])
    tabla_integridad.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDE8DD")),
        ("BACKGROUND", (0, 0), (0, -1), VERDE_CLARO),
        ("BACKGROUND", (1, 0), (1, -1), GRIS_CLARO),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_integridad)
    elementos.append(Spacer(1, 0.25 * cm))

    nota_integridad = (
        "Cualquier modificación posterior a un solo campo de esta evidencia "
        "(incluida la firma) genera un hash de integridad distinto al mostrado "
        "arriba, lo que permite detectar alteraciones del registro original."
    )
    elementos.append(Paragraph(nota_integridad, estilo_texto_legal))
    elementos.append(Spacer(1, 0.5 * cm))

    # ── PIE DE PÁGINA ────────────────────────────────────────────────────
    elementos.append(HRFlowable(width="100%", thickness=1.2, color=VERDE_PRIMARIO, spaceAfter=6))
    elementos.append(Paragraph(
        f"FitPro — Sistema de Gestión de Salud y Seguimiento Físico  |  "
        f"Documento generado automáticamente a partir del registro N.° {consentimiento.id}  |  "
        f"Este documento constituye evidencia del proceso de Habeas Data realizado con el paciente.",
        estilo_nota
    ))

    doc.build(elementos)
    buffer.seek(0)

    nombre_archivo = f"fitpro_evidencia_habeas_data_{paciente.nombre_completo.replace(' ', '_')}_{consentimiento.id}.pdf"

    _registrar_auditoria(
        db, current_user.id, "CONSENT_EVIDENCE_PDF_DOWNLOADED", request,
        patient_id=consentimiento.patient_id, entidad_tipo="patient_consent",
        entidad_id=consentimiento.id
    )

    logger.info(f"PDF de evidencia de consentimiento descargado: consent_id={consentimiento.id}, por={current_user.email}")

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={nombre_archivo}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# -----------------------------------------------
# POST: respaldo local de la base de datos (solo administradores)
# -----------------------------------------------
@router.post("/admin/backup")
async def generar_backup(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN]))
):
    """
    Genera una copia de respaldo local del archivo de base de datos SQLite.
    El respaldo se guarda en la misma carpeta de datos persistente de Docker,
    con marca de tiempo en el nombre. No se envía a ningún servicio externo.
    """
    ruta_bd = settings.DATABASE_URL.replace("sqlite:///", "")

    if not os.path.exists(ruta_bd):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se encontró el archivo de base de datos para respaldar"
        )

    carpeta_backups = os.path.join(os.path.dirname(os.path.abspath(ruta_bd)), "backups")
    os.makedirs(carpeta_backups, exist_ok=True)

    marca_tiempo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(carpeta_backups, f"fitpro_backup_{marca_tiempo}.db")

    shutil.copy2(ruta_bd, destino)

    _registrar_auditoria(
        db, current_user.id, "DB_BACKUP_CREATED", request,
        entidad_tipo="database", detalles=f"Respaldo creado: {os.path.basename(destino)}"
    )

    logger.info(f"Respaldo de base de datos creado por {current_user.email}: {destino}")

    return {"mensaje": "Respaldo generado exitosamente", "archivo": os.path.basename(destino)}