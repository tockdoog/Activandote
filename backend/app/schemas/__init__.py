# backend/app/schemas/__init__.py
# Punto de exportación central de todos los esquemas Pydantic del sistema.
# Permite importar cualquier schema con: from app.schemas import NombreSchema

from app.schemas.user import (
    UserRole,
    SubscriptionPlan,
    UserCreate,
    UserLogin,
    RefreshTokenRequest,
    UserResponse,
    TokenResponse,
)

from app.schemas.patient import (
    Genero,
    EstadoPaciente,
    PatientCreate,
    PatientUpdate,
    PatientResponse,
)

from app.schemas.evaluation import (
    CondicionFisica,
    RiesgoCardiovascular,
    EvaluationCreate,
    EvaluationResponse,
)

from pydantic import BaseModel
from typing import Optional, List


# -----------------------------------------------
# Esquemas genéricos compartidos por múltiples routers
# -----------------------------------------------

class PaginatedResponse(BaseModel):
    """
    Respuesta paginada genérica para cualquier listado del sistema.
    Incluye metadatos de paginación y la lista de ítems de la página actual.
    """
    total: int       # Total de registros en la base de datos
    page: int        # Página actual solicitada
    per_page: int    # Cantidad de registros por página
    pages: int       # Total de páginas disponibles
    items: List      # Registros de la página actual


class DashboardStats(BaseModel):
    """
    Estadísticas globales del entrenador para el panel de control.
    Todos los campos numéricos incluyen conteos e indicadores promedio.
    """
    total_pacientes: int
    pacientes_activos: int
    total_evaluaciones: int
    evaluaciones_este_mes: int
    pacientes_con_alerta: int
    promedio_imc: Optional[float]
    promedio_grasa: Optional[float]


# Exposición explícita de todos los símbolos del paquete
__all__ = [
    # Usuario
    "UserRole", "SubscriptionPlan", "UserCreate", "UserLogin",
    "RefreshTokenRequest", "UserResponse", "TokenResponse",
    # Paciente
    "Genero", "EstadoPaciente", "PatientCreate", "PatientUpdate", "PatientResponse",
    # Evaluación
    "CondicionFisica", "RiesgoCardiovascular", "EvaluationCreate", "EvaluationResponse",
    # Genéricos
    "PaginatedResponse", "DashboardStats",
]