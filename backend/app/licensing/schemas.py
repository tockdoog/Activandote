# backend/app/licensing/schemas.py
# Schemas Pydantic para el módulo de licencias mensuales.
# Incluye segundos_restantes para el countdown en tiempo real del frontend.

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# -----------------------------------------------
# Esquemas de respuesta (output)
# -----------------------------------------------

class LicenseStatusResponse(BaseModel):
    """
    Estado de la licencia enviado al frontend en cada verificación.
    El frontend usa segundos_restantes para el countdown en tiempo real.
    """
    # True = acceso permitido | False = mostrar pantalla de bloqueo
    acceso_permitido: bool

    # Mensaje descriptivo para mostrar al usuario
    mensaje: str

    # Días completos que faltan para el vencimiento (negativo = ya venció)
    dias_restantes: int

    # Segundos exactos hasta el vencimiento — usado por el countdown JS
    segundos_restantes: int

    # Fecha de vencimiento formateada en español para mostrar en UI
    fecha_vencimiento: str

    # True cuando quedan <= LICENSE_WARNING_DAYS días: activa banner + countdown
    mostrar_advertencia: bool


class LicenseResponse(BaseModel):
    """
    Detalle completo de la licencia del usuario para la vista de perfil.
    """
    id: int
    user_id: int
    esta_activa: bool
    esta_vigente: bool
    dias_restantes: int
    segundos_restantes: int
    renovaciones_count: int
    ultima_renovacion: Optional[datetime]
    fecha_vencimiento: str

    class Config:
        from_attributes = True


# -----------------------------------------------
# Esquemas de entrada (input)
# -----------------------------------------------

class RenovarLicenciaRequest(BaseModel):
    """
    Solicitud de renovación mensual.
    El backend compara clave directamente contra settings.LICENSE_KEY del .env.
    Sin hash, sin DB — comparación directa en texto plano con timing-safe.
    """
    clave: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Clave de renovación mensual del archivo .env"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "clave": "JULIO2025-FITPRO"
            }
        }