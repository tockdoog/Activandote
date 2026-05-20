@echo off
:: =============================================================
:: execution/windows/detener_programa.bat
:: Detiene todos los servicios de FitPro corriendo en Docker.
:: Usa "docker compose down" para detener y eliminar los
:: contenedores de forma limpia, preservando los volumenes
:: de datos (base de datos) para no perder informacion.
:: =============================================================

setlocal EnableDelayedExpansion
color 0C
title FitPro - Deteniendo Programa

:: -----------------------------------------------
:: Calcular ruta raiz del proyecto (2 niveles arriba)
:: -----------------------------------------------
set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..\..") do set "ROOT_DIR=%%~fi"

cls
echo.
echo  ======================================================
echo       FITPRO ^| CERRANDO EL PROGRAMA
echo  ======================================================
echo.
echo   Deteniendo todos los servicios...
echo.

:: -----------------------------------------------
:: Verificar que Docker este disponible
:: Si Docker no esta instalado o no corre, no hay nada que detener
:: -----------------------------------------------
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Docker no esta instalado. No hay servicios que detener.
    goto :FIN_SIN_DOCKER
)

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo   El motor de Docker no esta activo. No hay servicios corriendo.
    goto :FIN_SIN_DOCKER
)

:: -----------------------------------------------
:: Detectar la version de Docker Compose disponible
:: El mismo comando que se uso para levantar debe usarse para bajar
:: -----------------------------------------------
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    set "COMPOSE_CMD=docker compose"
) else (
    docker-compose --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "COMPOSE_CMD=docker-compose"
    ) else (
        echo   [ADVERTENCIA] Docker Compose no encontrado.
        echo   Los contenedores pueden seguir corriendo en Docker Desktop.
        goto :FIN_SIN_DOCKER
    )
)

:: -----------------------------------------------
:: Detener y eliminar los contenedores con "down"
:: "down" es seguro: detiene los servicios y elimina los contenedores
:: pero PRESERVA los volumenes de datos (base de datos SQLite)
:: para que no se pierda ninguna informacion del cliente
:: Se ejecuta desde la raiz donde esta el docker-compose.yml
:: -----------------------------------------------
cd /d "%ROOT_DIR%"
echo   Ejecutando: %COMPOSE_CMD% down
echo.
%COMPOSE_CMD% down
if %errorlevel% equ 0 (
    goto :FIN_OK
) else (
    color 0E
    echo.
    echo   [ADVERTENCIA] Puede haber ocurrido un error al detener.
    echo   Revisa el estado en Docker Desktop.
    goto :FIN_ERROR
)

:FIN_OK
:: -----------------------------------------------
:: Cierre exitoso
:: -----------------------------------------------
color 0A
echo.
echo  ======================================================
echo.
echo       FitPro se cerro correctamente.
echo.
echo       Todos los servicios fueron detenidos.
echo       Los datos del sistema estan guardados y seguros.
echo.
echo  ======================================================
echo.
color 0F
timeout /t 4 /nobreak >nul
endlocal
exit /b 0

:FIN_SIN_DOCKER
:: -----------------------------------------------
:: No habia nada corriendo
:: -----------------------------------------------
color 0A
echo.
echo  ======================================================
echo       No habia servicios de FitPro activos.
echo  ======================================================
echo.
color 0F
timeout /t 3 /nobreak >nul
endlocal
exit /b 0

:FIN_ERROR
color 0F
echo.
pause
endlocal
exit /b 1