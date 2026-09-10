#!/bin/bash

# =============================================================
# execution/mac/lanzador_programa.command
# Lanzador silencioso de FitPro con Docker para macOS.
# El usuario hace doble clic y se abre el navegador automaticamente.
# Proceso:
#   1. Calcula rutas absolutas desde la ubicacion del script
#   2. Verifica que docker-compose.yml exista en la raiz
#   3. Verifica que docker/.env exista
#   4. Verifica que Docker Desktop este instalado y activo
#   5. Detecta la IP de red local de macOS (para QR)
#   6. Escribe HOST_IP directamente en docker/.env (persistente)
#   7. Levanta los contenedores con docker compose up -d
#   8. Espera a que los servicios esten disponibles
#   9. Abre el navegador predeterminado en http://localhost
#
# CORRECCION IMPORTANTE (bug del QR con IP interna de Docker):
# Antes HOST_IP se pasaba solo como variable de entorno del proceso
# que ejecutaba "docker compose up". Ahora se escribe directamente en
# docker/.env, que el backend siempre lee via env_file, sin importar
# que comando haya iniciado los contenedores.
# =============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXEC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$EXEC_DIR/.." && pwd)"

COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE="$ROOT_DIR/docker/.env"

mostrar_error() {
    osascript -e "display dialog \"$1\" with title \"$2\" buttons {\"Cerrar\"} default button \"Cerrar\" with icon stop"
}

mostrar_aviso() {
    osascript -e "display dialog \"$1\" with title \"$2\" buttons {\"Cerrar\"} default button \"Cerrar\" with icon caution"
}

if [ ! -f "$COMPOSE_FILE" ]; then
    mostrar_error \
        "No se encontro el archivo docker-compose.yml.\n\nRuta esperada:\n$COMPOSE_FILE\n\nVerifica que el proyecto este completo y que el lanzador este en la carpeta: execution/mac/" \
        "FitPro - Archivo No Encontrado"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    mostrar_error \
        "No se encontro el archivo de configuracion.\n\nRuta esperada:\n$ENV_FILE\n\nSolucion: ejecuta primero instalar_programa.command para crear la configuracion inicial." \
        "FitPro - Configuracion Faltante"
    exit 1
fi

export PATH="$PATH:/usr/local/bin"

if ! docker info &>/dev/null; then
    mostrar_aviso \
        "Docker Desktop no esta activo.\n\nPara iniciar FitPro necesitas:\n\n1. Abre Docker Desktop desde Aplicaciones\n2. Espera a que el icono de la barra de menu deje de moverse\n   (30-60 segundos aproximadamente)\n3. Luego abre FitPro nuevamente" \
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

# -----------------------------------------------
# Detecta la IP de red local (WiFi/Ethernet) del Mac, descartando
# loopback, la red interna de Docker/WSL2 (172.x.x.x) y APIPA.
# -----------------------------------------------
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
    fi
}

# -----------------------------------------------
# Escribe (o limpia) la linea HOST_IP= dentro de docker/.env.
# Se elimina cualquier linea HOST_IP= previa y se agrega la actual
# al final, para que siempre quede una sola definicion vigente.
# -----------------------------------------------
actualizar_host_ip_env() {
    local ip="$1"
    local archivo="$ENV_FILE"
    [ -f "$archivo" ] || return

    grep -v '^HOST_IP=' "$archivo" > "${archivo}.tmp" 2>/dev/null
    mv "${archivo}.tmp" "$archivo"
    echo "HOST_IP=$ip" >> "$archivo"
}

HOST_IP="$(obtener_ip_red_local)"
actualizar_host_ip_env "$HOST_IP"

cd "$ROOT_DIR" || exit 1

# El backend lee HOST_IP desde docker/.env via "env_file" en
# docker-compose.yml, por eso ya no es necesario exportarla aqui.
$COMPOSE_CMD up -d

if [ $? -ne 0 ]; then
    mostrar_error \
        "Ocurrio un error al iniciar los servicios de FitPro.\n\nPara ver el detalle del error abre Terminal y ejecuta:\n$COMPOSE_CMD logs\n\nDirectorio del proyecto:\n$ROOT_DIR" \
        "FitPro - Error al Iniciar"
    exit 1
fi

sleep 6

open "http://localhost"

exit 0