#!/bin/bash
    echo "Docker instalado ✔"
fi

# -----------------------------------------------
# Verificar Docker Engine
# -----------------------------------------------
echo
echo "[3/5] Verificando Docker Engine..."

if ! docker ps &> /dev/null; then
    echo "[ERROR] Docker Desktop no está ejecutándose"
    ((ERRORS++))
else
    echo "Docker Engine activo ✔"
fi

# -----------------------------------------------
# Verificar Docker Compose
# -----------------------------------------------
echo
echo "[4/5] Verificando Docker Compose..."

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
# Verificar docker-compose.yml
# -----------------------------------------------
echo
echo "[5/5] Verificando archivos del proyecto..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$ROOT_DIR/docker-compose.yml" ]; then
    echo "docker-compose.yml encontrado ✔"
else
    echo "[ERROR] docker-compose.yml no encontrado"
    ((ERRORS++))
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