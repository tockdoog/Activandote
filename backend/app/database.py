# ./backend/app/database.py
# Configuración de la conexión SQLite con SQLAlchemy y manejo del ciclo de vida de sesiones

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from fastapi import HTTPException
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# SQLite requiere check_same_thread=False para funcionar con FastAPI (múltiples hilos)
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

# Motor de base de datos: echo=True muestra el SQL generado en consola (solo en DEBUG)
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)

# Fábrica de sesiones: sin autocommit para control manual de transacciones
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base única compartida por todos los modelos SQLAlchemy
Base = declarative_base()


def get_db():
    """
    Generador de sesión con cierre automático garantizado.
    Solo hace rollback en errores reales de base de datos,
    NO en excepciones HTTP normales (401, 404, etc.)
    """
    db = SessionLocal()
    try:
        yield db
    except HTTPException:
        # Las excepciones HTTP son flujo normal — no son errores de base de datos
        raise
    except Exception as e:
        # Solo aquí hay un error real de DB: rollback y log
        db.rollback()
        logger.error(f"Error en sesión de base de datos: {e}")
        raise
    finally:
        db.close()


def create_tables():
    """
    Crea las tablas al arrancar la aplicación.
    checkfirst=True evita errores si las tablas ya existen (arranques múltiples,
    workers concurrentes con uvicorn --workers > 1).
    """
    # Importar modelos para que SQLAlchemy los registre en Base.metadata
    from app.models import user, patient, evaluation  # noqa: F401

    try:
        # checkfirst=True: verifica si la tabla existe antes de intentar crearla
        Base.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("✅ Tablas verificadas/creadas exitosamente")
    except Exception as e:
        # En entornos con múltiples workers puede ocurrir una condición de carrera
        # leve — se registra como advertencia, no como error crítico
        logger.warning(f"Advertencia al crear tablas (puede ser condición de carrera): {e}")