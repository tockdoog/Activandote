# backend/app/database.py
# Configuración de la conexión SQLite con SQLAlchemy, manejo del ciclo de
# vida de sesiones y migraciones ligeras de columnas nuevas (sin Alembic).

from sqlalchemy import create_engine, text, inspect
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


def _migrar_columnas_faltantes() -> None:
    """
    Migración ligera para SQLite: agrega columnas nuevas a tablas que ya
    existían antes de esta versión, algo que create_all() no puede hacer
    (solo crea tablas nuevas, nunca altera tablas existentes).
    Verifica primero si la columna ya existe antes de intentar agregarla.
    """
    inspector = inspect(engine)

    if "patients" not in inspector.get_table_names():
        return  # La tabla se creará desde cero ya con la columna incluida

    columnas_actuales = [c["name"] for c in inspector.get_columns("patients")]

    # numero_documento: necesario para validar identidad en el módulo de Habeas Data
    if "numero_documento" not in columnas_actuales:
        with engine.connect() as conexion:
            conexion.execute(text("ALTER TABLE patients ADD COLUMN numero_documento VARCHAR(20)"))
            conexion.commit()
        logger.info("Migración: columna 'numero_documento' agregada a la tabla patients")


def create_tables():
    """
    Crea las tablas al arrancar la aplicación y aplica migraciones ligeras
    sobre tablas existentes. checkfirst=True evita errores si las tablas
    ya existen (arranques múltiples, workers concurrentes).
    """
    # Importar modelos para que SQLAlchemy los registre en Base.metadata
    from app.models import user, patient, evaluation, consent, audit  # noqa: F401

    try:
        # checkfirst=True: verifica si la tabla existe antes de intentar crearla
        Base.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("✅ Tablas verificadas/creadas exitosamente")

        # Migraciones ligeras sobre tablas que ya existían antes de este módulo
        _migrar_columnas_faltantes()

    except Exception as e:
        # En entornos con múltiples workers puede ocurrir una condición de carrera
        # leve — se registra como advertencia, no como error crítico
        logger.warning(f"Advertencia al crear/migrar tablas (puede ser condición de carrera): {e}")