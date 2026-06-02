#!/bin/bash

# =============================================================
# execution/mac/instalar_programa.command
# Instalador inicial de FitPro para macOS.
# Verifica prerequisitos, crea docker/.env y descarga imagenes.
# =============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXEC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$EXEC_DIR/.." && pwd)"

COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
DOCKER_DIR="$ROOT_DIR/docker"
ENV_FILE="$DOCKER_DIR/.env"

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
        "No se encontro el archivo docker-compose.yml.\n\nRuta esperada:\n$COMPOSE_FILE\n\nVerifica que el proyecto este completo y que el instalador este en la carpeta: execution/mac/" \
        "FitPro - Archivo No Encontrado"
    exit 1
fi

export PATH="$PATH:/usr/local/bin"

if ! docker info &>/dev/null; then
    mostrar_aviso \
        "Docker Desktop no esta activo.\n\nPara instalar FitPro necesitas:\n\n1. Abre Docker Desktop desde Aplicaciones\n2. Espera a que el icono de la barra de menu deje de moverse\n   (30-60 segundos aproximadamente)\n3. Luego abre el instalador nuevamente" \
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

obtener_ip_red_local() {
    local ip_preferida=""
    local ip_alternativa=""
    local ip=""

    for iface in $(ifconfig -l 2>/dev/null); do
        ip=$(ipconfig getifaddr "$iface" 2>/dev/null)
        [ -z "$ip" ] && continue
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
    else
        echo "localhost"
    fi
}

HOST_IP="$(obtener_ip_red_local)"

if [ ! -d "$DOCKER_DIR" ]; then
    mkdir -p "$DOCKER_DIR"
    if [ $? -ne 0 ]; then
        mostrar_error \
            "No se pudo crear la carpeta de configuracion:\n$DOCKER_DIR\n\nVerifica que tienes permisos de escritura en el proyecto." \
            "FitPro - Error de Permisos"
        exit 1
    fi
fi

cat > "$ENV_FILE" << EOF
# =============================================================
# FitPro - Configuracion de entorno
# Generado automaticamente por instalar_programa.command
# =============================================================

HOST_IP=$HOST_IP
EOF

if [ $? -ne 0 ]; then
    mostrar_error \
        "No se pudo crear el archivo de configuracion:\n$ENV_FILE\n\nVerifica que tienes permisos de escritura en la carpeta docker/." \
        "FitPro - Error al Crear Configuracion"
    exit 1
fi

cd "$ROOT_DIR" || exit 1

$COMPOSE_CMD pull

if [ $? -ne 0 ]; then
    mostrar_aviso \
        "Ocurrio un problema al descargar las imagenes de FitPro.\n\nVerifica tu conexion a internet e intenta de nuevo.\n\nSi el problema persiste, puedes intentar iniciar el programa directamente con lanzador_programa.command." \
        "FitPro - Error al Descargar"
    exit 1
fi

mostrar_info \
    "FitPro instalado correctamente.\n\nIP detectada para acceso movil: $HOST_IP\n\nPara iniciar el programa:\n→ Haz doble clic en lanzador_programa.command" \
    "FitPro - Instalacion Completa"

exit 0
