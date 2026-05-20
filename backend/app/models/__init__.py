# backend/app/models/__init__.py
# Exportación centralizada de todos los modelos ORM del sistema

from app.models.user import User, UserRole, SubscriptionPlan
from app.models.patient import Patient, Genero, EstadoPaciente
from app.models.evaluation import Evaluation, CondicionFisica, RiesgoCardiovascular

# Lista de todos los modelos para importación conveniente
__all__ = [
    "User", "UserRole", "SubscriptionPlan",
    "Patient", "Genero", "EstadoPaciente",
    "Evaluation", "CondicionFisica", "RiesgoCardiovascular",
]