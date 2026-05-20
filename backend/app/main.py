# backend/app/main.py
# Punto de entrada principal de la aplicación FastAPI - FitPro

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import time

from app.config import settings
from app.database import create_tables
from app.routers import auth, patients, evaluations, dashboard

# Importar el router del módulo de licencias
from app.licensing.router import router as licensing_router

# -----------------------------------------------
# Configuración del sistema de logging
# -----------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -----------------------------------------------
# Configuración de rate limiting por IP
# -----------------------------------------------
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejo del ciclo de vida de la aplicación.
    Ejecuta tareas de inicio y cierre controlado.
    """
    # === INICIO: Crear tablas de base de datos ===
    logger.info("Iniciando FitPro API...")
    create_tables()
    logger.info("Base de datos lista")

    # Registrar en log si CORS está en modo permisivo (red local)
    if settings.CORS_ALLOW_ALL:
        logger.warning(
            "CORS_ALLOW_ALL=True activo — todos los orígenes están permitidos. "
            "Recomendado solo para red local o desarrollo."
        )
    else:
        logger.info(f"CORS activo para orígenes: {settings.ALLOWED_ORIGINS}")

    yield
    # === CIERRE: Limpieza de recursos ===
    logger.info("Cerrando FitPro API...")


# -----------------------------------------------
# Instancia principal de la aplicación FastAPI
# -----------------------------------------------
app = FastAPI(
    title="FitPro API",
    description="""
    ## Sistema de Gestión Fitness y Seguimiento Clínico

    API REST para registro de pacientes, evaluaciones físicas periódicas
    y seguimiento estadístico del progreso en condición física.

    ### Funcionalidades:
    - 🔐 Autenticación JWT segura
    - 👥 Gestión de pacientes
    - 📊 Evaluaciones físicas completas
    - 📈 Dashboard estadístico
    - 📄 Exportación Excel/PDF
    - 🔑 Sistema de licencias mensuales
    """,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# -----------------------------------------------
# Middleware de rate limiting para protección DDoS
# -----------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# -----------------------------------------------
# Middleware CORS — configuración dinámica según entorno
#
# CORS_ALLOW_ALL=True  → acepta cualquier origen (red local / desarrollo)
#   - allow_origins=["*"]
#   - allow_credentials=False  ← obligatorio cuando origins es "*"
#     El token JWT se envía en el header Authorization (no como cookie),
#     por lo tanto credentials=False no afecta el funcionamiento.
#
# CORS_ALLOW_ALL=False → solo los orígenes en ALLOWED_ORIGINS
#   - allow_credentials=True  ← permite envío del header Authorization
# -----------------------------------------------
if settings.CORS_ALLOW_ALL:
    # Modo permisivo: cualquier origen (red local, múltiples dispositivos)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,        # Obligatorio con origins=["*"]
        allow_methods=settings.ALLOWED_METHODS,
        allow_headers=settings.ALLOWED_HEADERS,
        expose_headers=["Content-Disposition"]
    )
else:
    # Modo estricto: solo orígenes definidos en ALLOWED_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=settings.ALLOWED_METHODS,
        allow_headers=settings.ALLOWED_HEADERS,
        expose_headers=["Content-Disposition"]
    )

# -----------------------------------------------
# Middleware de hosts confiables (previene Host header injection)
# Se acepta cualquier host porque en red local la IP varía por máquina
# -----------------------------------------------
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)


@app.middleware("http")
async def agregar_cabeceras_seguridad(request: Request, call_next):
    """
    Middleware que añade cabeceras de seguridad HTTP a todas las respuestas.
    Previene XSS, clickjacking y otros ataques comunes.
    """
    start_time = time.time()
    response = await call_next(request)

    # Cabeceras de seguridad estándar
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # Header de tiempo de proceso para monitoreo
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time * 1000, 2)) + "ms"

    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Manejador global de errores de validación de Pydantic.
    Retorna mensajes de error en español y formato estandarizado.
    """
    errores = []
    for error in exc.errors():
        errores.append({
            "campo": " → ".join(str(loc) for loc in error["loc"]),
            "mensaje": error["msg"],
            "tipo": error["type"]
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detalle": "Error de validación", "errores": errores}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Manejador global de excepciones no controladas.
    Evita exponer detalles internos del sistema al cliente.
    """
    logger.error(f"Error no controlado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detalle": "Error interno del servidor. Contacte al administrador."}
    )


# -----------------------------------------------
# Registro de routers con prefijo /api/v1
# -----------------------------------------------
API_PREFIX = "/api/v1"

app.include_router(auth.router,         prefix=API_PREFIX)
app.include_router(patients.router,     prefix=API_PREFIX)
app.include_router(evaluations.router,  prefix=API_PREFIX)
app.include_router(dashboard.router,    prefix=API_PREFIX)

# Registrar el router del módulo de licencias mensuales
app.include_router(licensing_router,    prefix=API_PREFIX)


# -----------------------------------------------
# Endpoint de salud del sistema (health check)
# -----------------------------------------------
@app.get("/health", tags=["Sistema"])
async def health_check():
    """Verifica que la API está operativa. Usado por balanceadores de carga."""
    return {
        "estado": "operativo",
        "version": settings.APP_VERSION,
        "ambiente": settings.ENVIRONMENT
    }


@app.get("/", tags=["Sistema"])
async def root():
    """Endpoint raíz con información básica de la API."""
    return {
        "aplicacion": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "documentacion": "/docs" if settings.DEBUG else "No disponible en producción"
    }