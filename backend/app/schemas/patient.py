# backend/app/schemas/patient.py
# Esquemas Pydantic de validación y serialización para el modelo de Paciente.
# Cubre creación, actualización parcial y respuesta completa con metadata.

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
from enum import Enum


# -----------------------------------------------
# Enumeraciones de atributos del paciente
# -----------------------------------------------

class Genero(str, Enum):
    """Opciones de género con opción inclusiva de privacidad"""
    MASCULINO = "masculino"
    FEMENINO = "femenino"
    OTRO = "otro"
    PREFIERE_NO_DECIR = "prefiere_no_decir"


class EstadoPaciente(str, Enum):
    """Estado administrativo del registro del paciente"""
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    SUSPENDIDO = "suspendido"


# -----------------------------------------------
# Esquemas de entrada (request)
# -----------------------------------------------

class PatientCreate(BaseModel):
    """
    Esquema para el registro de un nuevo paciente.
    Incluye datos demográficos, contacto y medidas físicas iniciales de referencia.
    """
    nombre_completo: str = Field(..., min_length=3, max_length=100)
    edad: int = Field(..., ge=5, le=120)
    genero: Genero
    talla_metros: float = Field(..., ge=0.5, le=2.5)
    peso_inicial_kg: float = Field(..., ge=10.0, le=500.0)
    telefono: Optional[str] = Field(None, max_length=20)
    correo: Optional[str] = Field(None)
    fecha_nacimiento: Optional[date] = None
    fecha_ingreso: Optional[date] = None
    observaciones: Optional[str] = None
    objetivos: Optional[str] = None
    condicion_medica: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "nombre_completo": "María García López",
                "edad": 32,
                "genero": "femenino",
                "talla_metros": 1.65,
                "peso_inicial_kg": 72.5,
                "telefono": "3109876543",
                "correo": "maria@email.com",
                "objetivos": "Bajar de peso y mejorar condición cardiovascular"
            }
        }


class PatientUpdate(BaseModel):
    """
    Esquema para actualización parcial de paciente (PATCH semántico).
    Todos los campos son opcionales; solo se actualizan los que se envían.
    """
    nombre_completo: Optional[str] = Field(None, min_length=3, max_length=100)
    edad: Optional[int] = Field(None, ge=5, le=120)
    genero: Optional[Genero] = None
    talla_metros: Optional[float] = Field(None, ge=0.5, le=2.5)
    telefono: Optional[str] = None
    correo: Optional[str] = None
    observaciones: Optional[str] = None
    objetivos: Optional[str] = None
    condicion_medica: Optional[str] = None
    estado: Optional[EstadoPaciente] = None


# -----------------------------------------------
# Esquemas de salida (response)
# -----------------------------------------------

class PatientResponse(BaseModel):
    """
    Respuesta completa del paciente incluyendo metadata del sistema.
    El campo total_evaluaciones se calcula dinámicamente en el router.
    """
    id: int
    trainer_id: int
    nombre_completo: str
    edad: int
    genero: Genero
    talla_metros: float
    peso_inicial_kg: float
    telefono: Optional[str]
    correo: Optional[str]
    observaciones: Optional[str]
    objetivos: Optional[str]
    condicion_medica: Optional[str]
    estado: EstadoPaciente
    fecha_ingreso: Optional[date]
    created_at: datetime
    total_evaluaciones: Optional[int] = 0  # Calculado en router, no en BD

    class Config:
        from_attributes = True