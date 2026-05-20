# ./docker/README.md
# Documentación de la infraestructura Docker de FitPro

## Estructura de archivos Docker

```
./                               ← Raíz del proyecto
├── .dockerignore                ← Archivos excluidos del contexto de build
├── docker-compose.yml           ← Orquestador de contenedores
│
└── docker/                      ← Todo lo relacionado con Docker
    ├── README.md                ← Este archivo
    ├── .env                     ← Variables de entorno reales (NO subir a Git)
    ├── .env.example             ← Plantilla de variables de entorno
    │
    ├── backend/
    │   └── Dockerfile           ← Imagen del backend (FastAPI + Uvicorn)
    │
    └── nginx/
        ├── Dockerfile           ← Imagen del frontend (Nginx)
        ├── nginx.conf           ← Configuración del servidor virtual
        └── security_headers.conf← Cabeceras HTTP de seguridad (incluidas por nginx.conf)
```

---

## Arquitectura

```
Internet
    │
    ▼
┌─────────────────────────────────┐
│  Nginx (contenedor: fitpro_frontend) │  Puerto 80
│  ─────────────────────────────  │
│  /          → archivos estáticos│  HTML, CSS, JS desde /usr/share/nginx/html/
│  /api/      → proxy inverso     │  → backend:8000/api/v1/...
│  /health    → health check      │  → backend:8000/health
│  /img/      → imágenes estáticas│  Copiadas desde backend/img/ en el build
└──────────────┬──────────────────┘
               │ Red interna fitpro_red
               ▼
┌─────────────────────────────────┐
│  FastAPI (contenedor: fitpro_backend) │  Puerto 8000 (solo interno)
│  ─────────────────────────────  │
│  /api/v1/auth/...               │
│  /api/v1/patients/...           │
│  /api/v1/evaluations/...        │
│  /health                        │
└──────────────┬──────────────────┘
               │ Volumen Docker
               ▼
┌─────────────────────────────────┐
│  SQLite (volumen: fitpro_db_data)    │  /app/data/fitpro.db
└─────────────────────────────────┘
```

---

## Primer despliegue

### 1. Crear el archivo de variables de entorno

```bash
cp docker/.env.example docker/.env
```

### 2. Editar las variables obligatorias en `docker/.env`

**SECRET_KEY** — Generar una clave segura:
```bash
python -c "import secrets; print(secrets.token_hex(48))"
```
Pegar el resultado en `docker/.env`:
```dotenv
SECRET_KEY=el-resultado-del-comando-anterior
```

### 3. Construir y levantar los contenedores

```bash
docker compose up --build -d
```

- `--build` → reconstruye las imágenes (necesario en el primer deploy y después de cambios)
- `-d` → modo detached (en segundo plano)

### 4. Verificar que todo funciona

```bash
# Ver estado de los contenedores
docker compose ps

# Debe mostrar:
# fitpro_backend   → healthy
# fitpro_frontend  → running
```

Abrir en el navegador: **http://localhost**

---

## Comandos de uso cotidiano

```bash
# Ver logs en tiempo real (ambos contenedores)
docker compose logs -f

# Ver logs solo del backend
docker compose logs -f backend

# Ver logs solo del frontend (nginx)
docker compose logs -f frontend

# Detener los contenedores (los datos persisten)
docker compose down

# Detener Y BORRAR los datos de la base de datos
docker compose down -v

# Reiniciar solo el backend (después de cambios en el código)
docker compose up --build -d backend

# Reiniciar solo el frontend (después de cambios en CSS/JS/HTML)
docker compose up --build -d frontend

# Ver el estado de salud del backend
docker inspect fitpro_backend --format='{{.State.Health.Status}}'

# Acceder al shell del contenedor backend (para depuración)
docker exec -it fitpro_backend sh

# Ver tamaño de las imágenes construidas
docker images | grep fitpro
```

---

## Actualizar el código en producción

Después de hacer cambios en el código:

```bash
# 1. (Opcional) Detener los contenedores
docker compose down

# 2. Reconstruir con los cambios y levantar
docker compose up --build -d

# 3. Verificar que el despliegue fue exitoso
docker compose ps
docker compose logs -f --tail=50
```

---

## Variables de entorno (`docker/.env`)

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DEBUG` | `False` en producción | `False` |
| `ENVIRONMENT` | Entorno actual | `production` |
| `DATABASE_URL` | Ruta SQLite en el volumen | `sqlite:////app/data/fitpro.db` |
| `SECRET_KEY` | Clave para firmar JWT | `cadena-aleatoria-48-bytes` |
| `ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del token de acceso | `60` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Duración del token de refresco | `7` |
| `RATE_LIMIT_PER_MINUTE` | Peticiones por IP por minuto | `60` |
| `RATE_LIMIT_AUTH` | Límite en endpoints de auth | `10/minute` |
| `MIN_PASSWORD_LENGTH` | Longitud mínima de contraseña | `8` |
| `BCRYPT_ROUNDS` | Factor de coste bcrypt | `12` |

---

## Seguridad implementada

### Nginx (`security_headers.conf`)
| Cabecera | Protege contra |
|---|---|
| `X-Frame-Options: DENY` | Clickjacking (iframes maliciosos) |
| `X-Content-Type-Options: nosniff` | MIME sniffing (ejecutar JS disfrazado) |
| `X-XSS-Protection: 1; mode=block` | XSS en navegadores legacy |
| `Referrer-Policy` | Filtración de URLs en cabecera Referer |
| `Permissions-Policy` | Acceso a cámara, micrófono y geolocalización |
| `Content-Security-Policy` | Carga de recursos no autorizados, XSS |

### FastAPI (`main.py`)
- JWT con expiración configurable
- Rate limiting por IP (slowapi)
- CORS restringido a orígenes autorizados
- Validación de datos con Pydantic
- Contraseñas hasheadas con bcrypt (12 rondas)
- Usuario sin privilegios de root en el contenedor

### Docker
- El backend NO expone puertos al host (solo interno)
- Volumen nombrado para persistencia de datos
- Health check automático antes de enrutar tráfico
- Rotación de logs para evitar llenar el disco
- `.dockerignore` para no incluir archivos sensibles en el build

---

## Solución de problemas comunes

### El frontend carga pero la API no responde

```bash
# Verificar que el backend está healthy
docker compose ps

# Si está unhealthy, ver los logs del backend
docker compose logs backend --tail=50

# Verificar el health check manualmente
curl http://localhost/health
```

### Los estilos CSS no cargan

El bug más común: el Content-Security-Policy bloqueaba los estilos de Bootstrap CDN o Google Fonts. Ya está corregido en `security_headers.conf` con los orígenes permitidos correctos.

Si sigues viendo errores de CSP, abre las DevTools del navegador → pestaña Console y busca mensajes como `Refused to load stylesheet`.

### Error: "table already exists" al arrancar

Causa: hay más de 1 worker en Uvicorn. SQLite no soporta escrituras concurrentes.
Solución: el Dockerfile ya usa `--workers 1`. Si modificaste el CMD, restaurar a 1 worker.

### Los datos se borraron después de `docker compose down`

Causa: se usó `docker compose down -v` que borra los volúmenes.
El `docker compose down` sin `-v` preserva los datos.

### El contenedor backend no arranca (unhealthy)

```bash
# Ver el error específico
docker compose logs backend

# Errores comunes:
# - SECRET_KEY no definida en docker/.env
# - DATABASE_URL mal formada (necesita 4 slash: sqlite:////app/data/...)
# - Puerto 8000 ocupado por otro proceso en el host
```

---

## Diferencias entre desarrollo local y Docker

| Aspecto | Desarrollo local | Docker |
|---|---|---|
| Base de datos | `backend/fitpro.db` | `/app/data/fitpro.db` (volumen) |
| Puerto API | `http://localhost:8000` | Solo interno (nginx proxea) |
| Puerto Frontend | `http://localhost:5500` (Live Server) | `http://localhost` |
| DEBUG | `True` (Swagger activo) | `False` (Swagger oculto) |
| CORS | Permite `localhost:5500` | Solo `localhost:80` |
| Variables de entorno | `.env` local o config.py defaults | `docker/.env` |