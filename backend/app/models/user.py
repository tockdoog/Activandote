# backend/app/models/user.py
# Modelo de base de datos para entrenadores/usuarios del sistema

# backend/app/models/user.py

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TRAINER = "trainer"
    VIEWER = "viewer"


class SubscriptionPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre_completo = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    telefono = Column(String(20), nullable=True)

    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # native_enum=False → compatible con SQLite (guarda como VARCHAR)
    role = Column(SAEnum(UserRole, native_enum=False), default=UserRole.TRAINER, nullable=False)
    plan = Column(SAEnum(SubscriptionPlan, native_enum=False), default=SubscriptionPlan.FREE, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    last_login = Column(DateTime, nullable=True)

    # lazy="select" reemplaza "dynamic" (deprecado en SQLAlchemy 2.x)
    patients = relationship(
        "Patient",
        back_populates="trainer",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"