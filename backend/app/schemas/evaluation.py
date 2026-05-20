# backend/app/schemas/evaluation.py
# Esquemas Pydantic de validación y serialización para el modelo de Evaluación física.
# Cubre los tres bloques: composición corporal, indicadores de salud y evaluación funcional.

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from enum import Enum


# -----------------------------------------------
# Enumeraciones de condición y riesgo
# -----------------------------------------------

class CondicionFisica(str, Enum):
    """Clasificación general de la condición física del paciente"""
    EXCELENTE = "excelente"
    MUY_BUENA = "muy_buena"
    BUENA = "buena"
    REGULAR = "regular"
    DEFICIENTE = "deficiente"


class RiesgoCardiovascular(str, Enum):
    """Nivel de riesgo cardiovascular evaluado por el entrenador"""
    BAJO = "bajo"
    MODERADO = "moderado"
    ALTO = "alto"
    MUY_ALTO = "muy_alto"


# -----------------------------------------------
# Esquemas de entrada (request)
# -----------------------------------------------

class EvaluationCreate(BaseModel):
    """
    Esquema para el registro de una nueva evaluación física.
    Todos los campos de medición son opcionales para permitir evaluaciones parciales.
    La fecha es el único campo obligatorio.
    """
    fecha_evaluacion: date  # Único campo requerido

    # === Composición corporal ===
    peso_kg: Optional[float] = Field(None, ge=10.0, le=500.0)
    talla_metros: Optional[float] = Field(None, ge=0.5, le=2.5)
    porcentaje_grasa: Optional[float] = Field(None, ge=0.0, le=70.0)
    porcentaje_agua: Optional[float] = Field(None, ge=0.0, le=100.0)
    porcentaje_hueso: Optional[float] = Field(None, ge=0.0, le=30.0)
    musculo_kg: Optional[float] = Field(None, ge=0.0, le=200.0)
    condicion_fisica: Optional[CondicionFisica] = None
    edad_metabolica: Optional[int] = Field(None, ge=10, le=100)
    riesgo_cardiovascular: Optional[RiesgoCardiovascular] = None

    # === Indicadores de salud ===
    oxigenacion_porcentaje: Optional[float] = Field(None, ge=70.0, le=100.0)
    frecuencia_cardiaca_rpm: Optional[int] = Field(None, ge=30, le=250)
    horas_sueno: Optional[float] = Field(None, ge=0.0, le=24.0)
    tension_sistolica: Optional[int] = Field(None, ge=60, le=250)
    tension_diastolica: Optional[int] = Field(None, ge=40, le=150)
    perimetro_abdominal_cm: Optional[float] = Field(None, ge=40.0, le=200.0)

    # === Evaluación física funcional ===
    fc_reposo: Optional[int] = Field(None, ge=30, le=200)
    fc_post_esfuerzo: Optional[int] = Field(None, ge=50, le=250)
    fc_minuto_recuperacion: Optional[int] = Field(None, ge=30, le=250)
    fuerza_manual_der_kg: Optional[float] = Field(None, ge=0.0, le=100.0)
    fuerza_manual_izq_kg: Optional[float] = Field(None, ge=0.0, le=100.0)
    test_wells_cm: Optional[float] = Field(None, ge=-50.0, le=60.0)

    notas_entrenador: Optional[str] = None


# -----------------------------------------------
# Esquemas de salida (response)
# -----------------------------------------------

class EvaluationResponse(BaseModel):
    """
    Respuesta completa de evaluación incluyendo valores calculados automáticamente.
    imc e indice_ruffier son calculados por el router y no enviados por el cliente.
    """
    id: int
    patient_id: int
    trainer_id: int
    fecha_evaluacion: date
    numero_evaluacion: int  # Secuencial por paciente, calculado al crear

    # === Composición corporal ===
    peso_kg: Optional[float]
    talla_metros: Optional[float]
    porcentaje_grasa: Optional[float]
    porcentaje_agua: Optional[float]
    porcentaje_hueso: Optional[float]
    musculo_kg: Optional[float]
    imc: Optional[float]                        # Calculado automáticamente
    edad_metabolica: Optional[int]
    condicion_fisica: Optional[CondicionFisica]
    riesgo_cardiovascular: Optional[RiesgoCardiovascular]

    # === Indicadores de salud ===
    oxigenacion_porcentaje: Optional[float]
    frecuencia_cardiaca_rpm: Optional[int]
    horas_sueno: Optional[float]
    tension_sistolica: Optional[int]
    tension_diastolica: Optional[int]
    perimetro_abdominal_cm: Optional[float]

    # === Evaluación funcional ===
    fc_reposo: Optional[int]
    fc_post_esfuerzo: Optional[int]
    fc_minuto_recuperacion: Optional[int]
    indice_ruffier: Optional[float]             # Calculado automáticamente
    fuerza_manual_der_kg: Optional[float]
    fuerza_manual_izq_kg: Optional[float]
    test_wells_cm: Optional[float]

    notas_entrenador: Optional[str]
    tiene_alerta: bool                          # Generado por el sistema de alertas
    detalle_alerta: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True