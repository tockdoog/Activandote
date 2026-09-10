#!/bin/bash

# =============================================================
# execution/linux/verificar_sistema.sh
# Verifica que el sistema cumpla todos los requisitos para
# ejecutar FitPro en Linux. Util para diagnosticar problemas,
# incluyendo la deteccion de la IP de red local usada por el QR.
# =============================================================

clear

echo "======================================================"
echo "      FITPRO | VERIFICACION DEL SISTEMA"
echo "======================================================"

ERRORS=0
WARNINGS=0

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"

# -----------------------------------------------
# PASO 1: Verificar Docker instalado
# -----------------------------------------------
echo
echo "[1/5] Verificando Docker..."

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker no esta instalado."
    ((ERRORS++))
else
    docker --version
    echo "Docker instalado ✔"
fi

# -----------------------------------------------
# PASO 2: Verificar Docker Engine
# -----------------------------------------------
echo
echo "[2/5] Verificando Docker Engine..."

if ! docker ps &> /dev/null; then
    echo "[ERROR] Docker Engine no esta ejecutandose."
    ((ERRORS++))
else
    echo "Docker Engine activo ✔"
fi

# -----------------------------------------------
# PASO 3: Verificar Docker Compose
# -----------------------------------------------
echo
echo "[3/5] Verificando Docker Compose..."

if docker compose version &> /dev/null; then
    docker compose version
    echo "Docker Compose V2 ✔"
elif command -v docker-compose &> /dev/null; then
    docker-compose --version
    echo "Docker Compose V1 ✔"
else
    echo "[ERROR] Docker Compose no encontrado"
    ((ERRORS++))
fi

# -----------------------------------------------
# PASO 4: Verificar archivos del proyecto
# -----------------------------------------------
echo
echo "[4/5] Verificando archivos del proyecto..."

if [ -f "$ROOT_DIR/docker-compose.yml" ]; then
    echo "docker-compose.yml encontrado ✔"
else
    echo "[ERROR] docker-compose.yml no encontrado"
    ((ERRORS++))
fi

if [ -f "$ENV_FILE" ]; then
    echo "docker/.env encontrado ✔"
else
    echo "[ADVERTENCIA] docker/.env no encontrado — ejecuta instalar_programa.sh"
    ((WARNINGS++))
fi

# -----------------------------------------------
# PASO 5: Verificar IP de red local para el codigo QR
# Se usa la misma logica de deteccion que instalar_programa.sh y
# lanzar_programa.sh, para que el diagnostico refleje exactamente
# lo que esos scripts van a escribir en docker/.env.
# -----------------------------------------------
echo
echo "[5/5] Verificando IP de red local (para el QR)..."

HOST_IP=""
for ip in $(hostname -I 2>/dev/null); do
    [[ "$ip" == 127.* ]] && continue
    [[ "$ip" == 172.* ]] && continue
    [[ "$ip" == 169.254.* ]] && continue
    [[ "$ip" == *:* ]] && continue
    if [[ "$ip" == 192.168.* ]]; then
        HOST_IP="$ip"
        break
    fi
    if [[ "$ip" == 10.* ]] && [ -z "$HOST_IP" ]; then
        HOST_IP="$ip"
    fi
done

if [ -n "$HOST_IP" ]; then
    echo "IP de red local detectada: $HOST_IP ✔"
else
    echo "[ADVERTENCIA] No se detecto IP de red local. El QR usara localhost."
    ((WARNINGS++))
fi

if [ -f "$ENV_FILE" ]; then
    IP_EN_ENV="$(grep '^HOST_IP=' "$ENV_FILE" 2>/dev/null | cut -d= -f2)"
    if [ "$IP_EN_ENV" != "$HOST_IP" ]; then
        echo "[ADVERTENCIA] docker/.env tiene HOST_IP=\"$IP_EN_ENV\", distinto a la IP detectada ahora."
        echo "               Ejecuta lanzar_programa.sh o instalar_programa.sh para actualizarla."
        ((WARNINGS++))
    fi
fi

# -----------------------------------------------
# Resumen
# -----------------------------------------------
echo
echo "======================================================"
echo "RESUMEN"
echo "======================================================"
echo

echo "Errores: $ERRORS"
echo "Advertencias: $WARNINGS"

if [ $ERRORS -eq 0 ]; then
    echo
    echo "Sistema listo para ejecutar FitPro ✔"
else
    echo
    echo "Corrige los errores antes de continuar"
fi