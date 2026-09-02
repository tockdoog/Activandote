# backend/app/models/consent.py
# Modelos de base de datos para el módulo de Habeas Data:
# versiones del documento de consentimiento y evidencia de aceptación por paciente.

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ConsentDocumentVersion(Base):
    """
    Representa una versión del documento de tratamiento de datos / consentimiento
    informado. Cuando el contenido legal cambia se crea una NUEVA versión;
    las versiones anteriores nunca se editan ni se eliminan, para no alterar
    la evidencia de los consentimientos ya firmados con esa versión.
    """
    __tablename__ = "consent_document_versions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Código de versión visible, ej: "1.0", "1.1", "2.0"
    version = Column(String(20), nullable=False, unique=True, index=True)

    titulo = Column(String(200), nullable=False)

    # Contenido completo del documento (texto plano)
    contenido = Column(Text, nullable=False)

    # Solo una versión puede estar activa (vigente) a la vez
    activo = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<ConsentDocumentVersion(version={self.version}, activo={self.activo})>"


class PatientConsent(Base):
    """
    Evidencia INMUTABLE del proceso de Habeas Data / consentimiento informado
    realizado presencialmente con un paciente. Una vez creado, un registro
    de esta tabla NUNCA se modifica ni se elimina (no existen endpoints
    PUT/DELETE para este modelo): así se protege la integridad del historial.
    """
    __tablename__ = "patient_consents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True)
    trainer_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Profesional que ejecutó el proceso presencial con el paciente
    profesional_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Referencia a la versión exacta del documento que el paciente aceptó
    document_version_id = Column(Integer, ForeignKey("consent_document_versions.id", ondelete="RESTRICT"), nullable=False)
    version_documento = Column(String(20), nullable=False)  # Copia denormalizada para lectura rápida

    # Tipo de proceso registrado (permite extender el sistema a futuro)
    tipo_consentimiento = Column(String(60), nullable=False, default="tratamiento_datos_y_consentimiento_informado")

    # --- Checkboxes aceptados por el paciente ---
    acepta_datos_personales = Column(Boolean, nullable=False, default=False)
    acepta_datos_sensibles = Column(Boolean, nullable=False, default=False)
    acepta_consentimiento_informado = Column(Boolean, nullable=False, default=False)

    # --- Confirmación del profesional ---
    profesional_confirma = Column(Boolean, nullable=False, default=False)

    # --- Firma y validación de identidad ---
    firma_base64 = Column(Text, nullable=False)           # Imagen PNG en base64 capturada en pantalla
    firma_hash = Column(String(64), nullable=False)        # SHA-256 de la firma, para detectar alteraciones
    ultimos_4_digitos = Column(String(4), nullable=False)
    identidad_validada = Column(Boolean, nullable=False, default=False)

    # --- Confirmación final del paciente ---
    confirmacion_final = Column(Boolean, nullable=False, default=False)

    # --- Integridad de la evidencia completa ---
    hash_evidencia = Column(String(64), nullable=False, unique=True, index=True)

    # --- Metadatos de auditoría ---
    ip_origen = Column(String(45), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<PatientConsent(id={self.id}, patient_id={self.patient_id}, version={self.version_documento})>"