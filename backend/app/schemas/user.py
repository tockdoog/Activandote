# backend/app/schemas/user.py
# Esquemas Pydantic de validación y serialización para el modelo de Usuario/Entrenador.
# Incluye esquemas de autenticación, respuesta pública y renovación de tokens.

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# -----------------------------------------------
# Enumeraciones de roles y planes de suscripción
# -----------------------------------------------

class UserRole(str, Enum):
    """Roles disponibles para control de acceso en el sistema"""
    ADMIN = "admin"
    TRAINER = "trainer"
    VIEWER = "viewer"


class SubscriptionPlan(str, Enum):
    """Planes de suscripción SaaS disponibles"""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# -----------------------------------------------
# Esquemas de entrada (request)
# -----------------------------------------------

class UserCreate(BaseModel):
    """Esquema para el registro de un nuevo entrenador en el sistema"""
    nombre_completo: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    telefono: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8)

    class Config:
        json_schema_extra = {
            "example": {
                "nombre_completo": "Carlos Rodríguez",
                "email": "carlos@fitpro.com",
                "telefono": "3001234567",
                "password": "Seguro123!"
            }
        }


class UserLogin(BaseModel):
    """Esquema para el inicio de sesión con credenciales"""
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """
    Esquema para la solicitud de renovación de access token.
    El refresh_token se envía en el body como JSON (no como query param).
    """
    refresh_token: str


# -----------------------------------------------
# Esquemas de salida (response)
# -----------------------------------------------

class UserResponse(BaseModel):
    """Esquema de respuesta pública del usuario, sin exponer la contraseña hasheada"""
    id: int
    nombre_completo: str
    email: str
    telefono: Optional[str]
    role: UserRole
    plan: SubscriptionPlan
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True  # Permite construir desde objetos SQLAlchemy


class TokenResponse(BaseModel):
    """Respuesta completa de autenticación con par de tokens JWT y datos del usuario"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int          # Tiempo de expiración del access_token en segundos
    user: UserResponse