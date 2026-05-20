# ./docker/backend/Dockerfile
# Imagen del backend FitPro — FastAPI + Uvicorn sobre Python 3.11 slim
#
# CONTEXTO DE BUILD: raíz del proyecto (.)
# Todas las rutas COPY son relativas a la raíz del proyecto, NO a este Dockerfile.
# Esto es necesario porque docker-compose define context: . en la raíz.

# ─────────────────────────────────────────────────────────────────────────
# IMAGEN BASE — Python 3.11 slim (mínima, sin herramientas de compilación)
# Reduce el tamaño final de la imagen vs python:3.11 estándar (~200 MB menos)
# ─────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Variables de entorno de Python para el contenedor:
#   PYTHONDONTWRITEBYTECODE=1 → No genera archivos .pyc (ahorra espacio)
#   PYTHONUNBUFFERED=1        → Logs en tiempo real (stdout sin buffering)
#   PIP_NO_CACHE_DIR=1        → No guarda caché de pip (imagen más pequeña)
#   PIP_DISABLE_PIP_VERSION_CHECK=1 → Evita el aviso de versión en cada run
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema operativo mínimas:
#   curl → requerido por el healthcheck de docker-compose (CMD curl -f ...)
# Se limpia la caché de apt al final para no inflar la imagen
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo raíz del backend dentro del contenedor
WORKDIR /app

# ─────────────────────────────────────────────────────────────────────────
# DEPENDENCIAS PYTHON — Capa independiente para aprovechar el caché de Docker
# Si requirements.txt no cambia entre builds, Docker reutiliza esta capa
# sin reinstalar las dependencias (builds mucho más rápidos).
# Esta capa DEBE ir antes de copiar el código fuente.
# ─────────────────────────────────────────────────────────────────────────
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────
# CÓDIGO FUENTE — Se copia después de las dependencias para preservar el caché
# ─────────────────────────────────────────────────────────────────────────

# Módulos FastAPI: routers, modelos, schemas, utils, configuración
COPY backend/app/ ./app/

# Imágenes estáticas del backend.
# En Docker, el frontend y backend son contenedores separados.
# Nginx (frontend) sirve estas imágenes desde /usr/share/nginx/html/img/
# Esta copia es para que el backend tenga acceso local si algún endpoint las necesita.
COPY backend/img/ ./img/

# ─────────────────────────────────────────────────────────────────────────
# DIRECTORIO DE BASE DE DATOS
# El volumen Docker fitpro_db_data se monta en /app/data/
# para que los datos de SQLite persistan entre reinicios del contenedor.
# Se crea vacío aquí para que el usuario fitpro tenga permisos de escritura.
# ─────────────────────────────────────────────────────────────────────────
RUN mkdir -p /app/data

# ─────────────────────────────────────────────────────────────────────────
# SEGURIDAD — Usuario sin privilegios de root
# Ejecutar el proceso como root dentro del contenedor es una mala práctica:
# si hay una vulnerabilidad en FastAPI o sus dependencias, el atacante
# no tendría permisos de root en el sistema host.
# ─────────────────────────────────────────────────────────────────────────
RUN addgroup --system fitpro \
    && adduser --system --ingroup fitpro --no-create-home fitpro \
    && chown -R fitpro:fitpro /app

USER fitpro

# Puerto interno: solo accesible dentro de la red Docker fitpro_red.
# El puerto 8000 NO está expuesto al host; nginx lo alcanza por DNS interno.
EXPOSE 8000

# ─────────────────────────────────────────────────────────────────────────
# ARRANQUE — Uvicorn con UN SOLO WORKER
#
# Por qué solo 1 worker:
#   SQLite no soporta escrituras concurrentes desde múltiples procesos.
#   Con --workers 2+, todos los workers intentan crear las tablas al arrancar
#   simultáneamente, causando errores de "table already exists" o corrupción.
#   Con 1 worker esto no ocurre.
#
# --proxy-headers: le dice a Uvicorn que confíe en X-Forwarded-For y
#   X-Forwarded-Proto enviados por nginx. Necesario para que FastAPI
#   registre la IP real del cliente en lugar de la IP interna de nginx.
#
# --forwarded-allow-ips "*": acepta cabeceras X-Forwarded-For de nginx.
#   En producción con IP de nginx conocida, reemplazar "*" por esa IP.
# ─────────────────────────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]