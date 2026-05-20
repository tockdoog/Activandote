# backend/app/models/evaluation.py
# Modelo de base de datos para evaluaciones periódicas de condición física

# backend/app/models/evaluation.py

from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, Date, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class CondicionFisica(str, enum.Enum):
    EXCELENTE = "excelente"
    MUY_BUENA = "muy_buena"
    BUENA = "buena"
    REGULAR = "regular"
    DEFICIENTE = "deficiente"


class RiesgoCardiovascular(str, enum.Enum):
    BAJO = "bajo"
    MODERADO = "moderado"
    ALTO = "alto"
    MUY_ALTO = "muy_alto"


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    trainer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    fecha_evaluacion = Column(Date, nullable=False, index=True)
    numero_evaluacion = Column(Integer, nullable=False, default=1)

    # --- COMPOSICIÓN CORPORAL ---
    peso_kg = Column(Float, nullable=True)
    talla_metros = Column(Float, nullable=True)
    porcentaje_grasa = Column(Float, nullable=True)
    porcentaje_agua = Column(Float, nullable=True)
    porcentaje_hueso = Column(Float, nullable=True)
    musculo_kg = Column(Float, nullable=True)
    imc = Column(Float, nullable=True)
    edad_metabolica = Column(Integer, nullable=True)

    # native_enum=False → compatible con SQLite
    condicion_fisica = Column(SAEnum(CondicionFisica, native_enum=False), nullable=True)
    riesgo_cardiovascular = Column(SAEnum(RiesgoCardiovascular, native_enum=False), nullable=True)

    # --- INDICADORES DE SALUD ---
    oxigenacion_porcentaje = Column(Float, nullable=True)
    frecuencia_cardiaca_rpm = Column(Integer, nullable=True)
    horas_sueno = Column(Float, nullable=True)
    tension_sistolica = Column(Integer, nullable=True)
    tension_diastolica = Column(Integer, nullable=True)
    perimetro_abdominal_cm = Column(Float, nullable=True)

    # --- TEST RUFFIER ---
    fc_reposo = Column(Integer, nullable=True)
    fc_post_esfuerzo = Column(Integer, nullable=True)
    fc_minuto_recuperacion = Column(Integer, nullable=True)
    indice_ruffier = Column(Float, nullable=True)

    # --- FUERZA Y FLEXIBILIDAD ---
    fuerza_manual_der_kg = Column(Float, nullable=True)
    fuerza_manual_izq_kg = Column(Float, nullable=True)
    test_wells_cm = Column(Float, nullable=True)

    # --- NOTAS Y ALERTAS ---
    notas_entrenador = Column(Text, nullable=True)
    tiene_alerta = Column(Boolean, default=False, nullable=False)
    detalle_alerta = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    # Relación con paciente
    patient = relationship("Patient", back_populates="evaluaciones")

    # ← FIX: relación faltante con trainer (causaba error de mapper)
    trainer = relationship("User", foreign_keys=[trainer_id])

    def __repr__(self):
        return f"<Evaluation(id={self.id}, patient_id={self.patient_id}, fecha={self.fecha_evaluacion})>"