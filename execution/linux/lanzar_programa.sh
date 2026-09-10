#!/bin/bash

# =============================================================
# execution/linux/lanzar_programa.sh
# Inicia FitPro y abre el navegador.
#
# CORRECCION IMPORTANTE:
# Esta version anterior NO detectaba ninguna IP de red local, por lo
# que HOST_IP quedaba siempre vacia y el QR de acceso en red mostraba
# la IP interna de Docker (ej: 172.18.0.3) en vez de la IP LAN real.
# Ahora se detecta la IP con "hostname -I" y se escribe en
# docker/.env antes de levantar los contenedores.
# =============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env"

if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "Docker Compose no encontrado"
    exit 1
fi

# -----------------------------------------------
# Detecta la IP de red local (LAN/WiFi) de la maquina Linux,
# descartando loopback, la red interna de Docker (172.x.x.x),
# APIPA (169.254.x.x) e IPv6.
# -----------------------------------------------
obtener_ip_red_local() {
    local ip_preferida=""
    local ip_alternativa=""
    local ip=""

    # "hostname -I" lista todas las IPs asignadas a las interfaces activas
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

# -----------------------------------------------
# Escribe (o limpia) la linea HOST_IP= dentro de docker/.env.
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

cd "$ROOT_DIR" || exit

# El backend lee HOST_IP desde docker/.env via "env_file" en
# docker-compose.yml, por eso ya no es necesario exportarla aqui.
$COMPOSE_CMD up -d

if [ $? -ne 0 ]; then
    echo "Error iniciando FitPro"
    exit 1
fi

sleep 5

if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost
fi