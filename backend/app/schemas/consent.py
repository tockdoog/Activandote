# backend/app/schemas/consent.py
# Esquemas Pydantic del módulo de Habeas Data y consentimiento informado

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


# -----------------------------------------------
# Documento de consentimiento vigente
# -----------------------------------------------

class DocumentoVigenteResponse(BaseModel):
    """Documento de consentimiento actualmente activo, para mostrar al paciente"""
    id: int
    version: str
    titulo: str
    contenido: str
    created_at: datetime

    class Config:
        from_attributes = True


# -----------------------------------------------
# Estado de consentimiento de un paciente
# -----------------------------------------------

class ConsentEstadoResponse(BaseModel):
    """Indica si el paciente puede iniciar evaluaciones (tiene consentimiento vigente)"""
    tiene_consentimiento_valido: bool
    version_vigente: Optional[str] = None
    version_firmada: Optional[str] = None
    fecha_firma: Optional[datetime] = None
    requiere_actualizacion: bool = False  # True si firmó una versión distinta a la vigente
    numero_documento_registrado: bool = False  # True si el paciente ya tiene número de documento


# -----------------------------------------------
# Registro de un nuevo consentimiento (entrada)
# -----------------------------------------------

class ConsentCreate(BaseModel):
    """
    Datos capturados en pantalla durante el proceso presencial de consentimiento.
    Todos los campos booleanos de aceptación deben ser True para que el
    consentimiento se considere válido; el backend lo valida explícitamente.
    """
    acepta_datos_personales: bool
    acepta_datos_sensibles: bool
    acepta_consentimiento_informado: bool
    profesional_confirma: bool
    confirmacion_final: bool

    # Imagen de la firma capturada en el canvas, en formato data URL base64 (PNG)
    firma_base64: str = Field(..., min_length=100)

    # Últimos 4 dígitos del documento de identidad, ingresados por el paciente
    ultimos_4_digitos: str = Field(..., min_length=4, max_length=4)

    @field_validator("ultimos_4_digitos")
    @classmethod
    def validar_solo_numeros(cls, valor: str) -> str:
        """Verifica que los últimos 4 dígitos sean únicamente numéricos"""
        if not valor.isdigit():
            raise ValueError("Los últimos 4 dígitos deben ser numéricos")
        return valor

    @field_validator("firma_base64")
    @classmethod
    def validar_formato_firma(cls, valor: str) -> str:
        """Verifica que la firma tenga un formato de imagen base64 válido"""
        if not valor.startswith("data:image"):
            raise ValueError("Formato de firma inválido")
        return valor


# -----------------------------------------------
# Respuesta de un consentimiento registrado
# -----------------------------------------------

class ConsentResponse(BaseModel):
    """Respuesta tras registrar exitosamente el consentimiento (evidencia generada)"""
    id: int
    patient_id: int
    version_documento: str
    tipo_consentimiento: str
    acepta_datos_personales: bool
    acepta_datos_sensibles: bool
    acepta_consentimiento_informado: bool
    profesional_confirma: bool
    identidad_validada: bool
    confirmacion_final: bool
    hash_evidencia: str
    created_at: datetime

    class Config:
        from_attributes = True


# -----------------------------------------------
# Ítem de historial de consentimientos de un paciente
# -----------------------------------------------

class ConsentHistorialItem(BaseModel):
    """Resumen de un consentimiento histórico (sin exponer la imagen de firma)"""
    id: int
    version_documento: str
    tipo_consentimiento: str
    profesional_id: int
    nombre_profesional: Optional[str] = None
    identidad_validada: bool
    hash_evidencia: str
    created_at: datetime

    class Config:
        from_attributes = True


# -----------------------------------------------
# Detalle completo de evidencia (acceso restringido)
# -----------------------------------------------

class ConsentEvidenciaDetalle(ConsentHistorialItem):
    """Detalle completo incluyendo la firma — solo para roles autorizados"""
    firma_base64: str
    firma_hash: str
    ultimos_4_digitos: str
    ip_origen: Optional[str] = None