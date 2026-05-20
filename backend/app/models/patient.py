# backend/app/models/patient.py
# Modelo de base de datos para pacientes/clientes del entrenador


from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, Date, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class Genero(str, enum.Enum):
    MASCULINO = "masculino"
    FEMENINO = "femenino"
    OTRO = "otro"
    PREFIERE_NO_DECIR = "prefiere_no_decir"


class EstadoPaciente(str, enum.Enum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    SUSPENDIDO = "suspendido"


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    trainer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    nombre_completo = Column(String(100), nullable=False, index=True)
    edad = Column(Integer, nullable=False)
    fecha_nacimiento = Column(Date, nullable=True)

    # native_enum=False → compatible con SQLite
    genero = Column(SAEnum(Genero, native_enum=False), nullable=False)

    telefono = Column(String(20), nullable=True)
    correo = Column(String(150), nullable=True)

    talla_metros = Column(Float, nullable=False)
    peso_inicial_kg = Column(Float, nullable=False)

    observaciones = Column(Text, nullable=True)
    objetivos = Column(Text, nullable=True)
    condicion_medica = Column(Text, nullable=True)

    estado = Column(SAEnum(EstadoPaciente, native_enum=False), default=EstadoPaciente.ACTIVO, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    fecha_ingreso = Column(Date, nullable=True)

    trainer = relationship("User", back_populates="patients")

    # lazy="select" reemplaza "dynamic" (deprecado en SQLAlchemy 2.x)
    evaluaciones = relationship(
        "Evaluation",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="Evaluation.fecha_evaluacion",
        lazy="select"
    )

    def __repr__(self):
        return f"<Patient(id={self.id}, nombre={self.nombre_completo})>"