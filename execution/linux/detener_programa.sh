#!/bin/bash

# =============================================================
# execution/linux/detener_programa.sh
# Detiene los servicios Docker de FitPro
# =============================================================

clear

echo "======================================================"
echo "      FITPRO | DETENIENDO SERVICIOS"
echo "======================================================"
echo

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "Docker Compose no encontrado"
    exit 1
fi

cd "$ROOT_DIR" || exit

$COMPOSE_CMD down

if [ $? -eq 0 ]; then
    echo
    echo "Servicios detenidos correctamente ✔"
else
    echo
    echo "Error al detener servicios"
fi