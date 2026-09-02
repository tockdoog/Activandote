# backend/app/utils/consent.py
# Utilidades del módulo de Habeas Data: generación de hashes de evidencia
# y verificación de si un paciente tiene un consentimiento vigente y válido.

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.consent import ConsentDocumentVersion, PatientConsent


def hash_sha256(texto: str) -> str:
    """Calcula el hash SHA-256 de un texto y lo retorna en hexadecimal"""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def generar_hash_evidencia(datos: dict) -> str:
    """
    Genera el hash de integridad de una evidencia de consentimiento.
    Usa una serialización JSON canónica (claves ordenadas) para que el mismo
    contenido siempre produzca el mismo hash, permitiendo verificar más
    adelante que el registro no fue alterado.
    """
    contenido_canonico = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hash_sha256(contenido_canonico)


def obtener_documento_vigente(db: Session) -> Optional[ConsentDocumentVersion]:
    """Retorna la versión del documento de consentimiento actualmente activa"""
    return db.query(ConsentDocumentVersion).filter(
        ConsentDocumentVersion.activo == True
    ).order_by(ConsentDocumentVersion.created_at.desc()).first()


def sembrar_documento_inicial(db: Session) -> None:
    """
    Crea la primera versión del documento de consentimiento si todavía no
    existe ninguna. Se ejecuta una sola vez, al arrancar la aplicación.
    """
    existe = db.query(ConsentDocumentVersion).first()
    if existe:
        return

    documento_inicial = ConsentDocumentVersion(
        version="1.0",
        titulo="Tratamiento de Datos Personales, Datos Sensibles y Consentimiento Informado",
        contenido=(
            "ACTIVÁNDOTE POR TU VIDA — TRATAMIENTO DE DATOS Y CONSENTIMIENTO INFORMADO\n\n"
            "1. DATOS QUE SE RECOPILAN\n"
            "Recolectamos sus datos de identificación (nombre, edad, género, contacto) y "
            "los datos derivados de sus evaluaciones físicas y de salud (peso, composición "
            "corporal, signos vitales, condición física y demás indicadores registrados "
            "durante el proceso).\n\n"
            "2. FINALIDAD DEL TRATAMIENTO\n"
            "Estos datos se usan exclusivamente para: (a) realizar el seguimiento de su "
            "condición física y de salud a lo largo del tiempo, (b) generar reportes de "
            "evolución para usted y su entrenador/profesional a cargo, y (c) cumplir "
            "obligaciones legales de registro. No se comparten con terceros ni se usan con "
            "fines comerciales o publicitarios.\n\n"
            "3. DATOS SENSIBLES\n"
            "Algunos de los datos recopilados corresponden a datos sensibles de salud, "
            "protegidos por la Ley 1581 de 2012 y el Decreto 1377 de 2013 de la República "
            "de Colombia. El tratamiento de estos datos requiere su autorización previa, "
            "expresa e informada, la cual se solicita en este mismo proceso.\n\n"
            "4. SUS DERECHOS\n"
            "Usted tiene derecho a conocer, actualizar, rectificar y solicitar la supresión "
            "de sus datos personales, así como a revocar la autorización otorgada, salvo "
            "que exista un deber legal o contractual que impida su eliminación inmediata.\n\n"
            "5. ALMACENAMIENTO\n"
            "Toda la información se almacena de forma local y segura, sin enviarse a "
            "servicios externos, correos electrónicos ni aplicaciones de mensajería.\n\n"
            "6. CONSENTIMIENTO INFORMADO\n"
            "Al continuar, usted declara que un profesional le explicó el propósito de las "
            "evaluaciones físicas que se le realizarán, sus posibles molestias o riesgos "
            "leves asociados al esfuerzo físico, y que pudo resolver todas sus dudas antes "
            "de continuar."
        ),
        activo=True
    )

    db.add(documento_inicial)
    db.commit()


def tiene_consentimiento_valido(db: Session, patient_id: int) -> bool:
    """
    Retorna True si el paciente tiene un consentimiento completo, válido y
    correspondiente a la versión vigente del documento. Es la función que
    actúa como "puerta" antes de permitir iniciar evaluaciones.
    """
    documento_vigente = obtener_documento_vigente(db)
    if not documento_vigente:
        return False

    consentimiento = db.query(PatientConsent).filter(
        PatientConsent.patient_id == patient_id,
        PatientConsent.document_version_id == documento_vigente.id,
        PatientConsent.acepta_datos_personales == True,
        PatientConsent.acepta_datos_sensibles == True,
        PatientConsent.acepta_consentimiento_informado == True,
        PatientConsent.profesional_confirma == True,
        PatientConsent.identidad_validada == True,
        PatientConsent.confirmacion_final == True,
    ).order_by(PatientConsent.created_at.desc()).first()

    return consentimiento is not None


def obtener_ultimo_consentimiento(db: Session, patient_id: int) -> Optional[PatientConsent]:
    """Retorna el consentimiento más reciente registrado para un paciente, si existe"""
    return db.query(PatientConsent).filter(
        PatientConsent.patient_id == patient_id
    ).order_by(PatientConsent.created_at.desc()).first()


def timestamp_iso() -> str:
    """Retorna la fecha y hora actual en UTC, formato ISO 8601"""
    return datetime.now(timezone.utc).isoformat()