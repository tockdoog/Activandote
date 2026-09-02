# backend/app/models/audit.py
# Modelo de auditoría: registra cada acción sensible del sistema
# (creación y consulta de evidencia de consentimiento, backups, etc.)

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class AuditLog(Base):
    """
    Registro inmutable de auditoría. No existe ningún endpoint de edición
    o eliminación sobre esta tabla: solo se permite crear (INSERT-only)
    y consultar (solo administradores).
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Usuario que ejecutó la acción (NULL en acciones automáticas del sistema)
    usuario_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Paciente relacionado con la acción, si aplica
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True)

    # Acción realizada, ej: "CONSENT_CREATED", "CONSENT_EVIDENCE_VIEWED", "DB_BACKUP_CREATED"
    accion = Column(String(80), nullable=False, index=True)

    # Tipo y ID de la entidad afectada, ej: entidad_tipo="patient_consent", entidad_id=15
    entidad_tipo = Column(String(60), nullable=True)
    entidad_id = Column(Integer, nullable=True)

    # Detalle adicional en texto plano (nunca se guardan datos sensibles completos aquí)
    detalles = Column(Text, nullable=True)

    ip_origen = Column(String(45), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, accion={self.accion}, usuario_id={self.usuario_id})>"