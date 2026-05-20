#!/bin/bash

# =============================================================
# execution/linux/lanzar_programa.sh
# Inicia FitPro y abre el navegador
# =============================================================

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

$COMPOSE_CMD up -d

if [ $? -ne 0 ]; then
    echo "Error iniciando FitPro"
    exit 1
fi

sleep 5

if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost
fi