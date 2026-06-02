#!/bin/bash

# =============================================================
# execution/mac/verificar_sistema.command
# Verifica que el sistema cumpla todos los requisitos para
# ejecutar FitPro en macOS. Util para diagnosticar problemas.
# =============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXEC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$EXEC_DIR/.." && pwd)"

COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE="$ROOT_DIR/docker/.env"

export PATH="$PATH:/usr/local/bin"

ESTADO_MACOS="OK"
ESTADO_DOCKER_INSTALADO="OK"
ESTADO_DOCKER_ACTIVO="OK"
ESTADO_COMPOSE="OK"
ESTADO_COMPOSE_YML="OK"
ESTADO_ENV="OK"

DETALLE_MACOS=""
DETALLE_DOCKER_INSTALADO=""
DETALLE_DOCKER_ACTIVO=""
DETALLE_COMPOSE=""
DETALLE_IP=""

# --- macOS version ---
MACOS_VERSION="$(sw_vers -productVersion 2>/dev/null)"
if [ -z "$MACOS_VERSION" ]; then
    ESTADO_MACOS="FALLO"
    DETALLE_MACOS="No se pudo detectar la version de macOS."
else
    MAJOR=$(echo "$MACOS_VERSION" | cut -d. -f1)
    MINOR=$(echo "$MACOS_VERSION" | cut -d. -f2)
    if [ "$MAJOR" -gt 10 ] || { [ "$MAJOR" -eq 10 ] && [ "$MINOR" -ge 14 ]; }; then
        DETALLE_MACOS="macOS $MACOS_VERSION"
    else
        ESTADO_MACOS="FALLO"
        DETALLE_MACOS="macOS $MACOS_VERSION — Se requiere macOS 10.14 (Mojave) o superior."
    fi
fi

# --- Docker instalado ---
DOCKER_PATH="$(command -v docker 2>/dev/null)"
if [ -z "$DOCKER_PATH" ]; then
    ESTADO_DOCKER_INSTALADO="FALLO"
    DETALLE_DOCKER_INSTALADO="docker no encontrado en PATH."
else
    DETALLE_DOCKER_INSTALADO="$(docker --version 2>/dev/null)"
fi

# --- Docker activo ---
if [ "$ESTADO_DOCKER_INSTALADO" = "OK" ]; then
    if ! docker info &>/dev/null; then
        ESTADO_DOCKER_ACTIVO="FALLO"
        DETALLE_DOCKER_ACTIVO="Instalado pero no esta corriendo. Abrelo desde Aplicaciones."
    else
        DETALLE_DOCKER_ACTIVO="Motor Docker activo y respondiendo."
    fi
else
    ESTADO_DOCKER_ACTIVO="FALLO"
    DETALLE_DOCKER_ACTIVO="No verificado (Docker no esta instalado)."
fi

# --- Docker Compose ---
if [ "$ESTADO_DOCKER_INSTALADO" = "OK" ]; then
    if docker compose version &>/dev/null 2>&1; then
        DETALLE_COMPOSE="Compose V2 — $(docker compose version 2>/dev/null)"
    elif command -v docker-compose &>/dev/null; then
        DETALLE_COMPOSE="Compose V1 — $(docker-compose --version 2>/dev/null)"
    else
        ESTADO_COMPOSE="FALLO"
        DETALLE_COMPOSE="No disponible. Reinicia Docker Desktop."
    fi
else
    ESTADO_COMPOSE="FALLO"
    DETALLE_COMPOSE="No verificado (Docker no esta instalado)."
fi

# --- docker-compose.yml ---
if [ ! -f "$COMPOSE_FILE" ]; then
    ESTADO_COMPOSE_YML="FALLO"
fi

# --- docker/.env ---
if [ ! -f "$ENV_FILE" ]; then
    ESTADO_ENV="FALLO"
fi

# --- IP de red local ---
HOST_IP=""
for iface in $(ifconfig -l 2>/dev/null); do
    ip=$(ipconfig getifaddr "$iface" 2>/dev/null)
    [ -z "$ip" ] && continue
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

[ -n "$HOST_IP" ] && DETALLE_IP="$HOST_IP" || DETALLE_IP="No detectada (QR usara localhost)"

# --- Construir resumen ---
ok="✅"
fallo="❌"

linea_macos="$( [ "$ESTADO_MACOS" = "OK" ] && echo "$ok" || echo "$fallo" )  macOS: $DETALLE_MACOS"
linea_docker="$( [ "$ESTADO_DOCKER_INSTALADO" = "OK" ] && echo "$ok" || echo "$fallo" )  Docker: $DETALLE_DOCKER_INSTALADO"
linea_activo="$( [ "$ESTADO_DOCKER_ACTIVO" = "OK" ] && echo "$ok" || echo "$fallo" )  Motor Docker: $DETALLE_DOCKER_ACTIVO"
linea_compose="$( [ "$ESTADO_COMPOSE" = "OK" ] && echo "$ok" || echo "$fallo" )  Docker Compose: $DETALLE_COMPOSE"
linea_yml="$( [ "$ESTADO_COMPOSE_YML" = "OK" ] && echo "$ok" || echo "$fallo" )  docker-compose.yml: $( [ "$ESTADO_COMPOSE_YML" = "OK" ] && echo "Encontrado" || echo "No encontrado en $COMPOSE_FILE" )"
linea_env="$( [ "$ESTADO_ENV" = "OK" ] && echo "$ok" || echo "$fallo" )  docker/.env: $( [ "$ESTADO_ENV" = "OK" ] && echo "Encontrado" || echo "No encontrado — ejecuta instalar_programa.command" )"
linea_ip="🌐  IP de red local: $DETALLE_IP"

MENSAJE="$linea_macos\n$linea_docker\n$linea_activo\n$linea_compose\n$linea_yml\n$linea_env\n\n$linea_ip"

# --- Mostrar resultado ---
hay_fallos=false
for estado in "$ESTADO_MACOS" "$ESTADO_DOCKER_INSTALADO" "$ESTADO_DOCKER_ACTIVO" "$ESTADO_COMPOSE" "$ESTADO_COMPOSE_YML" "$ESTADO_ENV"; do
    [ "$estado" = "FALLO" ] && hay_fallos=true && break
done

if [ "$hay_fallos" = false ]; then
    osascript -e "display dialog \"Todas las verificaciones pasaron correctamente.\n\n$MENSAJE\n\nPuedes iniciar FitPro con lanzador_programa.command\" with title \"FitPro - Sistema Listo ✅\" buttons {\"Aceptar\"} default button \"Aceptar\" with icon note"
else
    osascript -e "display dialog \"Se encontraron problemas que impiden iniciar FitPro.\n\n$MENSAJE\n\nRevisa los items marcados con ❌ antes de continuar.\" with title \"FitPro - Problemas Detectados ❌\" buttons {\"Cerrar\"} default button \"Cerrar\" with icon stop"
fi

exit 0
