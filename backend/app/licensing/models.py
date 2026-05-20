# backend/app/licensing/models.py
# Modelo de base de datos para el sistema de licencias mensuales.
# NOTA: La clave de renovación ya NO se guarda en la DB.
# Se lee directamente desde el .env (settings.LICENSE_KEY).
# La DB solo guarda el historial de renovaciones para auditoría.

from sqlalchemy import Column, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class License(Base):
    """
    Registro de licencia por usuario.
    Guarda el historial de renovaciones y el estado de bloqueo manual.
    La fecha de vencimiento real viene del .env (LICENSE_EXPIRY),
    pero se cachea aquí para mostrarla al usuario sin leer el .env en cada request.
    """
    __tablename__ = "licenses"

    # Clave primaria autoincremental
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Relación 1:1 con users — cada usuario tiene una sola licencia
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )

    # -----------------------------------------------
    # Estado de la licencia
    # -----------------------------------------------

    # Permite bloquear manualmente a un usuario sin cambiar el .env
    esta_activa = Column(Boolean, default=True, nullable=False)

    # Contador de renovaciones exitosas (auditoría)
    renovaciones_count = Column(Integer, default=0, nullable=False)

    # Fecha y hora de la última renovación exitosa (auditoría)
    ultima_renovacion = Column(DateTime, nullable=True)

    # Notas internas del administrador (opcional)
    notas_admin = Column(Text, nullable=True)

    # Timestamps de auditoría automáticos
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    # -----------------------------------------------
    # Relación ORM hacia el usuario
    # -----------------------------------------------
    user = relationship("User", backref="license", uselist=False)

    def __repr__(self):
        return (
            f"<License(id={self.id}, user_id={self.user_id}, "
            f"activa={self.esta_activa}, renovaciones={self.renovaciones_count})>"
        )