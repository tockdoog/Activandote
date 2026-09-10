#!/bin/bash

# =============================================================
# execution/mac/instalar_programa.command
# Instalador inicial de FitPro para macOS.
# Verifica prerequisitos, crea/actualiza docker/.env y descarga imagenes.
#
# CORRECCION IMPORTANTE (bug critico de configuracion perdida):
# La version anterior generaba docker/.env desde cero con SOLO la
# linea "HOST_IP=...", borrando SECRET_KEY, CORS_ALLOW_ALL, licencia
# y el resto de variables necesarias para que el backend funcione
# correctamente. Ahora se copia docker/.env.example completo (igual
# que hace el instalador de Windows) y solo se agrega o actualiza la
# linea HOST_IP=, preservando todas las demas variables.
# =============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXEC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$EXEC_DIR/.." && pwd)"

COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
DOCKER_DIR="$ROOT_DIR/docker"
ENV_FILE="$DOCKER_DIR/.env"
ENV_EXAMPLE="$DOCKER_DIR/.env.example"

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

# -----------------------------------------------
# Detecta la IP de red local (WiFi/Ethernet) del Mac, descartando
# loopback, la red interna de Docker/WSL2 (172.x.x.x) y APIPA.
# Si no se detecta ninguna, devuelve cadena vacia (no "localhost"),
# para que el backend la trate de forma consistente con el resto
# de scripts como "no configurada" en vez de un valor invalido.
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

# -----------------------------------------------
# Crear docker/.env desde la plantilla completa (.env.example) si
# todavia no existe, en vez de generarlo desde cero con una sola
# linea. Esto preserva SECRET_KEY, CORS_ALLOW_ALL, licencia, etc.
# Si docker/.env ya existe (instalaciones previas), se conserva tal
# cual esta y solo se actualiza la linea HOST_IP mas abajo.
# -----------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    if [ ! -f "$ENV_EXAMPLE" ]; then
        mostrar_error \
            "No existe docker/.env.example.\n\nRuta esperada:\n$ENV_EXAMPLE\n\nEl proyecto esta incompleto." \
            "FitPro - Plantilla No Encontrada"
        exit 1
    fi

    cp "$ENV_EXAMPLE" "$ENV_FILE"
    if [ $? -ne 0 ]; then
        mostrar_error \
            "No se pudo crear el archivo de configuracion:\n$ENV_FILE\n\nVerifica que tienes permisos de escritura en la carpeta docker/." \
            "FitPro - Error al Crear Configuracion"
        exit 1
    fi
fi

# -----------------------------------------------
# Actualizar (o agregar) la linea HOST_IP= dentro de docker/.env,
# sin tocar el resto de variables ya presentes en el archivo.
# -----------------------------------------------
grep -v '^HOST_IP=' "$ENV_FILE" > "${ENV_FILE}.tmp" 2>/dev/null
mv "${ENV_FILE}.tmp" "$ENV_FILE"
echo "HOST_IP=$HOST_IP" >> "$ENV_FILE"

cd "$ROOT_DIR" || exit 1

$COMPOSE_CMD pull

if [ $? -ne 0 ]; then
    mostrar_aviso \
        "Ocurrio un problema al descargar las imagenes de FitPro.\n\nVerifica tu conexion a internet e intenta de nuevo.\n\nSi el problema persiste, puedes intentar iniciar el programa directamente con lanzador_programa.command." \
        "FitPro - Error al Descargar"
    exit 1
fi

mostrar_info \
    "FitPro instalado correctamente.\n\nIP detectada para acceso movil: ${HOST_IP:-No detectada (se usara localhost)}\n\nPara iniciar el programa:\n→ Haz doble clic en lanzador_programa.command" \
    "FitPro - Instalacion Completa"

exit 0