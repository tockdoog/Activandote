@echo off
:: =============================================================
:: execution/windows/verificar_sistema.bat
:: Verifica requisitos del sistema para ejecutar FitPro con Docker.
:: Usa !errorlevel! con delayed expansion para capturas confiables.
:: =============================================================

setlocal EnableDelayedExpansion
color 0C
title FitPro - Verificacion del Sistema

:: -----------------------------------------------
:: Calcular ruta raiz del proyecto (2 niveles arriba)
:: -----------------------------------------------
set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..\..") do set "ROOT_DIR=%%~fi"
set "COMPOSE_FILE=%ROOT_DIR%\docker-compose.yml"
set "ENV_FILE=%ROOT_DIR%\docker\.env"
set "ENV_EXAMPLE=%ROOT_DIR%\docker\.env.example"

set /a ERRORES=0
set /a ADVERTENCIAS=0

cls
echo.
echo  ======================================================
echo       FITPRO ^| VERIFICACION DEL SISTEMA
echo  ======================================================
echo.

:: -----------------------------------------------
:: VERIFICACION 1: Version de Windows
:: Leer desde el registro es mas confiable que wmic o ver
:: -----------------------------------------------
echo  [1/7] Verificando sistema operativo...

:: Leer nombre del producto desde el registro de Windows
for /f "tokens=2,*" %%a in (
    'reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v ProductName 2^>nul ^| findstr "ProductName"'
) do set "WIN_NAME=%%b"

:: Leer numero de build actual desde el registro
for /f "tokens=2,*" %%a in (
    'reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v CurrentBuild 2^>nul ^| findstr "CurrentBuild"'
) do set "WIN_BUILD=%%b"

if defined WIN_NAME (
    echo        Sistema : !WIN_NAME!
) else (
    echo        Sistema : No detectado
)

if defined WIN_BUILD (
    echo        Build   : !WIN_BUILD!
    :: Docker Desktop requiere build 17763 (Windows 10 1809) o superior
    if !WIN_BUILD! LSS 17763 (
        echo        [ERROR] Windows demasiado antiguo para Docker Desktop.
        echo               Se requiere Windows 10 version 1809 ^(build 17763^) o superior.
        set /a ERRORES+=1
    ) else (
        echo        [OK] Version de Windows compatible con Docker Desktop.
    )
) else (
    echo        [ADVERTENCIA] No se pudo verificar el build exacto de Windows.
    set /a ADVERTENCIAS+=1
)

:: -----------------------------------------------
:: VERIFICACION 2: WSL 2
:: Docker Desktop en Windows usa WSL 2 como motor por defecto
:: -----------------------------------------------
echo.
echo  [2/7] Verificando WSL 2...

wsl --status >nul 2>&1
set "EL_WSL=!errorlevel!"

if "!EL_WSL!" neq "0" (
    echo        [ERROR] WSL no esta instalado.
    echo.
    echo        Solucion paso a paso:
    echo          1. Abre PowerShell como Administrador
    echo          2. Ejecuta el comando: wsl --install
    echo          3. Reinicia el computador cuando lo solicite
    echo          4. Vuelve a ejecutar este verificador
    set /a ERRORES+=1
) else (
    echo        [OK] WSL disponible y activo.
)

:: -----------------------------------------------
:: VERIFICACION 3: Docker Desktop instalado
:: Buscar el ejecutable docker en el PATH del sistema
:: -----------------------------------------------
echo.
echo  [3/7] Verificando Docker Desktop instalado...

where docker >nul 2>&1
set "EL_WHERE=!errorlevel!"

if "!EL_WHERE!" neq "0" (
    echo        [ERROR] Docker no esta instalado o no esta en el PATH.
    echo.
    echo        Solucion paso a paso:
    echo          1. Ve a: https://www.docker.com/products/docker-desktop
    echo          2. Descarga "Docker Desktop for Windows"
    echo          3. Instala como Administrador
    echo          4. Reinicia el computador
    echo          5. Abre Docker Desktop y acepta los terminos
    echo          6. Vuelve a ejecutar este verificador
    set /a ERRORES+=1
) else (
    :: Capturar version de Docker para mostrar al usuario
    for /f "tokens=3" %%v in ('docker --version 2^>^&1') do (
        set "DOCKER_VER=%%v"
        set "DOCKER_VER=!DOCKER_VER:,=!"
    )
    echo        [OK] Docker !DOCKER_VER! instalado correctamente.
)

:: -----------------------------------------------
:: VERIFICACION 4: Motor de Docker corriendo
:: Si Docker Desktop esta cerrado, docker ps falla
:: -----------------------------------------------
echo.
echo  [4/7] Verificando motor de Docker activo...

docker ps >nul 2>&1
set "EL_PS=!errorlevel!"

if "!EL_PS!" neq "0" (
    echo        [ERROR] El motor de Docker no esta corriendo.
    echo.
    echo        Solucion paso a paso:
    echo          1. Abre "Docker Desktop" desde el menu Inicio
    echo          2. Espera a que el icono de la ballena en la bandeja
    echo             del sistema deje de parpadear ^(aprox. 30-60 seg^)
    echo          3. Vuelve a ejecutar este verificador
    set /a ERRORES+=1
) else (
    echo        [OK] Motor de Docker activo y respondiendo.
)

:: -----------------------------------------------
:: VERIFICACION 5: Docker Compose disponible
:: V2 usa "docker compose", V1 usa "docker-compose"
:: -----------------------------------------------
echo.
echo  [5/7] Verificando Docker Compose...

docker compose version >nul 2>&1
set "EL_CV2=!errorlevel!"

if "!EL_CV2!" equ "0" (
    for /f "tokens=4" %%v in ('docker compose version 2^>^&1') do set "COMPOSE_VER=%%v"
    echo        [OK] Docker Compose V2 ^(!COMPOSE_VER!^) - comando: "docker compose"
) else (
    docker-compose --version >nul 2>&1
    set "EL_CV1=!errorlevel!"
    if "!EL_CV1!" equ "0" (
        for /f "tokens=3" %%v in ('docker-compose --version 2^>^&1') do set "COMPOSE_VER=%%v"
        echo        [OK] Docker Compose V1 ^(!COMPOSE_VER!^) - comando: "docker-compose"
    ) else (
        echo        [ERROR] Docker Compose no encontrado.
        echo               Reinstala Docker Desktop para obtenerlo automaticamente.
        set /a ERRORES+=1
    )
)

:: -----------------------------------------------
:: VERIFICACION 6: Archivos del proyecto
:: -----------------------------------------------
echo.
echo  [6/7] Verificando archivos del proyecto...

if exist "%COMPOSE_FILE%" (
    echo        [OK] docker-compose.yml encontrado.
) else (
    echo        [ERROR] docker-compose.yml no encontrado en:
    echo               %ROOT_DIR%
    set /a ERRORES+=1
)

if exist "%ENV_FILE%" (
    echo        [OK] docker\.env encontrado.
) else (
    if exist "%ENV_EXAMPLE%" (
        echo        [ADVERTENCIA] docker\.env no existe pero hay .env.example.
        echo               Ejecuta Instalador_programa.bat para crearlo.
        set /a ADVERTENCIAS+=1
    ) else (
        echo        [ERROR] Ni docker\.env ni .env.example existen.
        set /a ERRORES+=1
    )
)

:: -----------------------------------------------
:: VERIFICACION 7: Puerto 80 disponible para nginx
:: -----------------------------------------------
echo.
echo  [7/7] Verificando puerto 80...

netstat -an 2>nul | findstr ":80 " | findstr "LISTENING" >nul
set "EL_PORT=!errorlevel!"

if "!EL_PORT!" equ "0" (
    echo        [ADVERTENCIA] Puerto 80 en uso por otro proceso.
    echo               FitPro puede fallar al iniciar.
    echo               Para identificar el proceso: netstat -aon ^| findstr ":80 "
    set /a ADVERTENCIAS+=1
) else (
    echo        [OK] Puerto 80 disponible.
)

:: -----------------------------------------------
:: RESUMEN FINAL
:: -----------------------------------------------
echo.
echo  ------------------------------------------------------
echo   RESUMEN
echo  ------------------------------------------------------
echo.

if !ERRORES! gtr 0 (
    color 0C
    echo   ERRORES CRITICOS : !ERRORES!  ^<-- Deben resolverse antes de continuar
)
if !ADVERTENCIAS! gtr 0 (
    echo   ADVERTENCIAS     : !ADVERTENCIAS!
)
if !ERRORES! equ 0 (
    if !ADVERTENCIAS! equ 0 (
        color 0A
        echo   ESTADO : Sistema listo. Ejecuta Instalador_programa.bat
    ) else (
        color 0A
        echo   ESTADO : Listo con advertencias menores.
    )
)

echo.
echo   Proyecto: %ROOT_DIR%
echo.
echo  ======================================================
echo.
color 0F
pause
endlocal