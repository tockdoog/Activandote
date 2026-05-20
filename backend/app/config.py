# backend/app/config.py
# Configuración central con variables de entorno — compatible con desarrollo local, Docker y red local

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json


class Settings(BaseSettings):
    """
    Configuración central de FitPro.
    Los valores se leen del archivo .env (Docker) o del entorno del sistema.
    Si una variable no existe, usa el valor por defecto definido aquí.
    """

    # -----------------------------------------------
    # Información de la aplicación
    # -----------------------------------------------
    APP_NAME: str = "FitPro - Gestión Fitness"
    APP_VERSION: str = "1.0.0"

    # DEBUG=True muestra /docs, SQL en consola y stack traces detallados
    # En Docker producción se sobreescribe con DEBUG=False desde .env
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # -----------------------------------------------
    # Base de datos SQLite
    # Desarrollo local: archivo en la carpeta del backend
    # Docker: ruta al volumen persistente /app/data/
    # -----------------------------------------------
    DATABASE_URL: str = "sqlite:///./fitpro.db"

    # -----------------------------------------------
    # Seguridad JWT
    # -----------------------------------------------
    SECRET_KEY: str = "dev-secret-key-cambia-esto-en-produccion-2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -----------------------------------------------
    # CORS — Control de orígenes permitidos
    # En Docker/red local NO se usa CORS entre cliente y nginx (mismo origen),
    # solo aplica en desarrollo con Live Server u otros puertos.
    # Acepta: JSON array  → ["http://url1","http://url2"]
    #         Separado por comas → http://url1,http://url2
    # -----------------------------------------------
    ALLOWED_ORIGINS: List[str] = [
        # Desarrollo local con Live Server / VS Code
        "http://localhost",
        "http://localhost:80",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        # Permite archivos abiertos directamente (file://)
        "null",
    ]

    # -----------------------------------------------
    # CORS — Modo permisivo para red local
    # True  → acepta CUALQUIER origen (útil en red local o desarrollo)
    #         En este modo allow_credentials se desactiva automáticamente
    # False → usa solo ALLOWED_ORIGINS (recomendado en producción internet)
    # -----------------------------------------------
    CORS_ALLOW_ALL: bool = False

    ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    ALLOWED_HEADERS: List[str] = ["*"]

    # -----------------------------------------------
    # Rate limiting
    # -----------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH: str = "10/minute"

    # -----------------------------------------------
    # Política de contraseñas
    # -----------------------------------------------
    MIN_PASSWORD_LENGTH: int = 8
    BCRYPT_ROUNDS: int = 12

    # -----------------------------------------------
    # Límites de pacientes por plan
    # -----------------------------------------------
    MAX_PATIENTS_FREE: int = 10
    MAX_PATIENTS_PRO: int = 100
    MAX_PATIENTS_ENTERPRISE: int = 99999

    # -----------------------------------------------
    # SISTEMA DE LICENCIAS MENSUALES
    # -----------------------------------------------
    LICENSE_KEY: str = "DEMO-FITPRO-2025"
    LICENSE_EXPIRY: str = "2099-12-31"
    LICENSE_WARNING_DAYS: int = 5

    # -----------------------------------------------
    # Validador: parsea ALLOWED_ORIGINS desde .env
    # Acepta JSON array o lista separada por comas
    # Ejemplo .env:  ALLOWED_ORIGINS=http://192.168.1.10,http://192.168.1.20
    # Ejemplo .env:  ALLOWED_ORIGINS=["http://192.168.1.10","http://192.168.1.20"]
    # -----------------------------------------------
    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parsear_origenes(cls, valor):
        """Convierte el valor de la variable de entorno a lista de strings."""
        # Si ya es lista (valor por defecto), no hacer nada
        if isinstance(valor, list):
            return valor

        if isinstance(valor, str):
            valor = valor.strip()

            # Intentar parsear como JSON array: ["url1","url2"]
            if valor.startswith("["):
                try:
                    return json.loads(valor)
                except json.JSONDecodeError:
                    pass

            # Parsear como lista separada por comas: url1,url2,url3
            return [origen.strip() for origen in valor.split(",") if origen.strip()]

        return valor

    class Config:
        # Busca el archivo .env en la carpeta actual al ejecutar uvicorn
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Instancia única compartida por toda la aplicación (patrón Singleton)
settings = Settings()