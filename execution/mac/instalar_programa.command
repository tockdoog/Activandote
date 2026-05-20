#!/bin/bash
    echo
    echo "[ERROR] Docker Desktop no está corriendo."
    echo
    echo "Abre Docker Desktop y espera unos segundos."
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
# PASO 4: Crear .env si no existe
# -----------------------------------------------
echo
echo "[4/5] Verificando archivo .env..."

if [ -f "$ENV_FILE" ]; then
    echo "docker/.env ya existe ✔"
else
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo "docker/.env creado ✔"
    else
        echo
        echo "[ERROR] No existe .env.example"
        exit 1
    fi
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
open http://localhost

echo
echo "FitPro iniciado correctamente ✔"