#!/bin/bash

# =============================================================
# execution/mac/detener_programa.command
# Detiene todos los contenedores de FitPro en macOS.
# =============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXEC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$EXEC_DIR/.." && pwd)"

COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

mostrar_error() {
    osascript -e "display dialog \"$1\" with title \"$2\" buttons {\"Cerrar\"} default button \"Cerrar\" with icon stop"
}

mostrar_aviso() {
    osascript -e "display dialog \"$1\" with title \"$2\" buttons {\"Cerrar\"} default button \"Cerrar\" with icon caution"
}

mostrar_info() {
    osascript -e "display dialog \"$1\" with title \"$2\" buttons {\"Aceptar\"} default button \"Aceptar\" with icon note"
}

if [ ! -f "$COMPOSE_FILE" ]; then
    mostrar_error \
        "No se encontro el archivo docker-compose.yml.\n\nRuta esperada:\n$COMPOSE_FILE\n\nVerifica que el proyecto este completo y que el script este en la carpeta: execution/mac/" \
        "FitPro - Archivo No Encontrado"
    exit 1
fi

export PATH="$PATH:/usr/local/bin"

if ! docker info &>/dev/null; then
    mostrar_aviso \
        "Docker Desktop no esta activo.\n\nSi FitPro estaba corriendo, es posible que ya se haya detenido al cerrar Docker Desktop.\n\nPuedes abrir Docker Desktop y luego intentar detener nuevamente si los contenedores aun aparecen activos." \
        "FitPro - Docker No Esta Activo"
    exit 1
fi

if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    mostrar_error \
        "Docker Compose no esta disponible.\n\nReinicia Docker Desktop para obtener Compose V2 incluido automaticamente." \
        "FitPro - Docker Compose No Encontrado"
    exit 1
fi

cd "$ROOT_DIR" || exit 1

$COMPOSE_CMD down

if [ $? -ne 0 ]; then
    mostrar_aviso \
        "Ocurrio un problema al detener FitPro.\n\nPara ver el detalle abre Terminal y ejecuta:\n$COMPOSE_CMD logs\n\nDirectorio del proyecto:\n$ROOT_DIR" \
        "FitPro - Error al Detener"
    exit 1
fi

mostrar_info \
    "FitPro se ha detenido correctamente.\n\nTodos los contenedores han sido cerrados.\nTus datos estan guardados y se conservaran al volver a iniciar." \
    "FitPro - Detenido"

exit 0
