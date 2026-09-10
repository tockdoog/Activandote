#!/bin/bash

# =============================================================
# execution/linux/instalar_programa.sh
# Instalador inicial de FitPro para Linux.
# Verifica prerequisitos, crea/actualiza docker/.env (incluyendo
# la IP de red local para el codigo QR) y levanta los contenedores.
#
# NOTA: se detecta la IP de red local y se escribe DIRECTAMENTE en
# docker/.env (linea HOST_IP=), no como variable de entorno del
# proceso que ejecuta "docker compose up". Esto es lo que hace que
# el backend siempre la lea correctamente via env_file, sin importar
# con que comando se levanten despues los contenedores.
# =============================================================

clear

echo "======================================================"
echo "      FITPRO | INSTALADOR CON DOCKER"
echo "======================================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE="$ROOT_DIR/docker/.env"
ENV_EXAMPLE="$ROOT_DIR/docker/.env.example"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo
    echo "[ERROR] No se encontro docker-compose.yml en: $ROOT_DIR"
    exit 1
fi

# -----------------------------------------------
# PASO 1: Verificar Docker instalado
# -----------------------------------------------
echo
echo "[1/5] Verificando Docker..."

if ! command -v docker &> /dev/null; then
    echo
    echo "[ERROR] Docker no esta instalado."
    echo "Instalalo desde: https://docs.docker.com/engine/install/"
    exit 1
fi

echo "Docker instalado ✔"

# -----------------------------------------------
# PASO 2: Verificar Docker Engine activo
# -----------------------------------------------
echo
echo "[2/5] Verificando Docker Engine..."

if ! docker info &> /dev/null; then
    echo
    echo "[ERROR] Docker Engine no esta corriendo."
    echo
    echo "Inicia el servicio con: sudo systemctl start docker"
    exit 1
fi

echo "Docker Engine activo ✔"

# -----------------------------------------------
# PASO 3: Verificar Docker Compose
# -----------------------------------------------
echo
echo "[3/5] Verificando Docker Compose..."

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
    echo "Docker Compose V2 detectado ✔"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
    echo "Docker Compose V1 detectado ✔"
else
    echo
    echo "[ERROR] Docker Compose no encontrado."
    exit 1
fi

# -----------------------------------------------
# PASO 4: Crear .env si no existe y detectar IP de red local
#
# Si docker/.env no existe, se copia completo desde .env.example
# (preservando SECRET_KEY, CORS, licencia, etc.). Luego, sin importar
# si el archivo era nuevo o ya existia, se detecta la IP de red local
# de la maquina y se actualiza (o agrega) la linea HOST_IP= dentro
# del archivo, para que el codigo QR del dashboard muestre la IP
# correcta de la red LAN en vez de la IP interna de Docker.
# -----------------------------------------------
echo
echo "[4/5] Verificando configuracion (.env) y detectando IP de red..."

if [ -f "$ENV_FILE" ]; then
    echo "docker/.env ya existe ✔"
else
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo "docker/.env creado desde .env.example ✔"
    else
        echo
        echo "[ERROR] No existe docker/.env.example"
        exit 1
    fi
fi

# Detecta la IP de red local (LAN/WiFi), descartando loopback,
# la red interna de Docker (172.x.x.x), APIPA e IPv6.
obtener_ip_red_local() {
    local ip_preferida=""
    local ip_alternativa=""
    local ip=""

    for ip in $(hostname -I 2>/dev/null); do
        [[ "$ip" == 127.* ]] && continue
        [[ "$ip" == 172.* ]] && continue
        [[ "$ip" == 169.254.* ]] && continue
        [[ "$ip" == *:* ]] && continue

        if [[ "$ip" == 192.168.* ]]; then
            ip_preferida="$ip"
            break
        fi
        if [[ "$ip" == 10.* ]] && [ -z "$ip_alternativa" ]; then
            ip_alternativa="$ip"
        fi
    done

    if [ -n "$ip_preferida" ]; then
        echo "$ip_preferida"
    elif [ -n "$ip_alternativa" ]; then
        echo "$ip_alternativa"
    fi
}

HOST_IP="$(obtener_ip_red_local)"

# Elimina cualquier linea HOST_IP= previa y agrega la actual al final,
# sin tocar el resto de variables del archivo.
grep -v '^HOST_IP=' "$ENV_FILE" > "${ENV_FILE}.tmp" 2>/dev/null
mv "${ENV_FILE}.tmp" "$ENV_FILE"
echo "HOST_IP=$HOST_IP" >> "$ENV_FILE"

if [ -n "$HOST_IP" ]; then
    echo "IP de red local detectada: $HOST_IP ✔"
else
    echo "[ADVERTENCIA] No se detecto IP de red local. El QR usara localhost."
fi

# -----------------------------------------------
# PASO 5: Levantar contenedores
# -----------------------------------------------
echo
echo "[5/5] Iniciando servicios Docker..."
echo

cd "$ROOT_DIR" || exit

$COMPOSE_CMD up --build -d

if [ $? -ne 0 ]; then
    echo
    echo "[ERROR] Falló el inicio de los contenedores."
    echo
    echo "Ver logs con:"
    echo "$COMPOSE_CMD logs"
    exit 1
fi

echo
echo "Contenedores iniciados correctamente ✔"

echo
echo "Esperando que el sistema inicie..."
sleep 6

# Abrir navegador
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost
fi

echo
echo "FitPro iniciado correctamente ✔"