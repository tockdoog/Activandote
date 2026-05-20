@echo off
:: =============================================================
:: execution/windows/Instalador_programa.bat
:: Instala FitPro con Docker: levanta contenedores y crea
:: el acceso directo en el Escritorio.
:: Usa !errorlevel! para deteccion confiable de errores.
:: El shortcut se crea via archivo .ps1 temporal para evitar
:: problemas de escaping con comillas en PowerShell inline.
:: =============================================================

setlocal EnableDelayedExpansion
color 0C
title FitPro - Instalador

:: -----------------------------------------------
:: Calcular ruta raiz del proyecto (2 niveles arriba)
:: -----------------------------------------------
set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..\..") do set "ROOT_DIR=%%~fi"
set "COMPOSE_FILE=%ROOT_DIR%\docker-compose.yml"
set "ENV_FILE=%ROOT_DIR%\docker\.env"
set "ENV_EXAMPLE=%ROOT_DIR%\docker\.env.example"
set "LAUNCHER_VBS=%SCRIPT_DIR%lanzador_programa.vbs"
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\FitPro.lnk"

cls
echo.
echo  ======================================================
echo       FITPRO ^| INSTALADOR CON DOCKER
echo  ======================================================
echo.
echo   Proyecto : %ROOT_DIR%
echo   Launcher : %LAUNCHER_VBS%
echo   Escritorio: %SHORTCUT_PATH%
echo.
echo  No cierres esta ventana durante la instalacion.
echo  ------------------------------------------------------

:: -----------------------------------------------
:: PASO 1: Verificar Docker instalado
:: -----------------------------------------------
echo.
echo  [PASO 1/6] Verificando Docker Desktop...

where docker >nul 2>&1
set "EL=!errorlevel!"

if "!EL!" neq "0" (
    color 0C
    echo.
    echo  [ERROR] Docker no esta instalado o no esta en el PATH.
    echo          Descargalo en: https://www.docker.com/products/docker-desktop
    echo          Luego reinstala marcando "Add to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=3" %%v in ('docker --version 2^>^&1') do (
    set "DOCKER_VER=%%v"
    set "DOCKER_VER=!DOCKER_VER:,=!"
)
echo        Docker !DOCKER_VER! instalado. [OK]

:: -----------------------------------------------
:: PASO 2: Verificar motor de Docker activo
:: Usar "docker ps" en lugar de "docker info"
:: porque ps es mas rapido y confiable para este chequeo
:: -----------------------------------------------
echo.
echo  [PASO 2/6] Verificando motor de Docker activo...

docker ps >nul 2>&1
set "EL=!errorlevel!"

if "!EL!" neq "0" (
    color 0C
    echo.
    echo  [ERROR] El motor de Docker no esta corriendo.
    echo.
    echo  Pasos para solucionarlo:
    echo    1. Abre "Docker Desktop" desde el menu Inicio
    echo    2. Espera a que el icono de la ballena en la bandeja
    echo       del sistema se quede estatico (30-60 segundos)
    echo    3. Cierra esta ventana y vuelve a ejecutar el instalador
    echo.
    pause
    exit /b 1
)
echo        Motor de Docker activo. [OK]

:: -----------------------------------------------
:: PASO 3: Detectar version de Docker Compose
:: -----------------------------------------------
echo.
echo  [PASO 3/6] Detectando Docker Compose...

docker compose version >nul 2>&1
set "EL=!errorlevel!"

if "!EL!" equ "0" (
    set "COMPOSE_CMD=docker compose"
    for /f "tokens=4" %%v in ('docker compose version 2^>^&1') do set "COMPOSE_VER=%%v"
    echo        Docker Compose V2 ^(!COMPOSE_VER!^). [OK]
) else (
    docker-compose --version >nul 2>&1
    set "EL=!errorlevel!"
    if "!EL!" equ "0" (
        set "COMPOSE_CMD=docker-compose"
        for /f "tokens=3" %%v in ('docker-compose --version 2^>^&1') do set "COMPOSE_VER=%%v"
        echo        Docker Compose V1 ^(!COMPOSE_VER!^). [OK]
    ) else (
        color 0C
        echo        [ERROR] Docker Compose no encontrado. Reinstala Docker Desktop.
        pause
        exit /b 1
    )
)

:: -----------------------------------------------
:: PASO 4: Crear docker/.env desde .env.example si no existe
:: -----------------------------------------------
echo.
echo  [PASO 4/6] Verificando configuracion (.env)...

if exist "!ENV_FILE!" (
    echo        docker\.env ya existe. Configuracion conservada. [OK]
) else (
    if exist "!ENV_EXAMPLE!" (
        copy /Y "!ENV_EXAMPLE!" "!ENV_FILE!" >nul
        set "EL=!errorlevel!"
        if "!EL!" equ "0" (
            echo        docker\.env creado desde .env.example. [OK]
            echo.
            echo        [IMPORTANTE] Revisa %ENV_FILE%
            echo        y ajusta las variables antes de produccion.
        ) else (
            echo        [ADVERTENCIA] No se pudo crear .env. Verifica permisos en: %ROOT_DIR%\docker\
        )
    ) else (
        color 0C
        echo        [ERROR] No existe docker\.env.example. Proyecto incompleto.
        pause
        exit /b 1
    )
)

:: -----------------------------------------------
:: PASO 5: Construir imagenes y levantar contenedores
:: --build  → reconstruye con los ultimos cambios del codigo
:: -d       → detached, corre en segundo plano
:: -----------------------------------------------
echo.
echo  [PASO 5/6] Iniciando servicios con Docker...
echo        Comando: !COMPOSE_CMD! up --build -d
echo        La primera vez puede tardar 5-10 minutos.
echo.

cd /d "%ROOT_DIR%"
!COMPOSE_CMD! up --build -d
set "EL=!errorlevel!"

if "!EL!" neq "0" (
    color 0C
    echo.
    echo  [ERROR] Fallo al levantar los servicios Docker.
    echo.
    echo  Para ver el detalle del error ejecuta:
    echo    cd %ROOT_DIR%
    echo    !COMPOSE_CMD! logs
    echo.
    pause
    exit /b 1
)

echo.
echo        Contenedores iniciados. [OK]
echo.
echo        Esperando que los servicios esten listos...
timeout /t 8 /nobreak >nul

:: Verificar salud del backend si curl esta disponible en el sistema
where curl >nul 2>&1
if "!errorlevel!" equ "0" (
    set /a INTENTOS=0
    :HEALTH_LOOP
    set /a INTENTOS+=1
    curl -s -o nul -w "%%{http_code}" http://localhost/health 2>nul | findstr "200" >nul
    if "!errorlevel!" equ "0" (
        echo        Backend respondiendo en /health. [OK]
        goto :HEALTH_OK
    )
    if !INTENTOS! LSS 6 (
        echo        Intento !INTENTOS!/5 - Esperando servicios...
        timeout /t 3 /nobreak >nul
        goto :HEALTH_LOOP
    )
    echo        [ADVERTENCIA] Servicios tardando mas de lo esperado.
    echo               Verifica con: !COMPOSE_CMD! logs
    :HEALTH_OK
)

:: -----------------------------------------------
:: PASO 6: Crear acceso directo en el Escritorio
::
:: Se escribe un archivo .ps1 temporal para evitar el problema
:: de escaping de comillas con PowerShell en linea (inline).
:: El metodo inline con ^ y ; es fragil cuando hay rutas con
:: caracteres especiales o versiones distintas de PowerShell.
:: -----------------------------------------------
echo.
echo  [PASO 6/6] Creando acceso directo en el Escritorio...

:: Verificar que el VBS lanzador exista antes de crear el shortcut
if not exist "%LAUNCHER_VBS%" (
    echo        [ERROR] lanzador_programa.vbs no encontrado en:
    echo        %LAUNCHER_VBS%
    echo        Verifica que el archivo exista en execution\windows\
    goto :FIN
)

:: Definir ruta del script PowerShell temporal
set "PS_TEMP=%TEMP%\fitpro_shortcut.ps1"

:: Escribir el script PowerShell en el archivo temporal
:: Cada linea es un comando PowerShell independiente
:: Las rutas quedan embebidas como literales por expansion de batch
> "%PS_TEMP%" (
    echo $ws = New-Object -ComObject WScript.Shell
    echo $s = $ws.CreateShortcut('%SHORTCUT_PATH%')
    echo $s.TargetPath = 'wscript.exe'
    echo $s.Arguments = '/nologo "%LAUNCHER_VBS%"'
    echo $s.WorkingDirectory = '%ROOT_DIR%'
    echo $s.Description = 'FitPro - Sistema de Gestion Fitness Profesional'
    echo $s.WindowStyle = 1
    echo $s.Save()
)

:: Ejecutar el script PowerShell temporal
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_TEMP%"
set "EL=!errorlevel!"

:: Eliminar el archivo temporal independientemente del resultado
del "%PS_TEMP%" >nul 2>&1

:: Confirmar si el shortcut fue creado exitosamente
if exist "%SHORTCUT_PATH%" (
    echo        Acceso directo "FitPro" creado en el Escritorio. [OK]
) else (
    echo        [ADVERTENCIA] No se pudo crear el acceso directo.
    echo.
    echo        Puedes crearlo manualmente:
    echo          - Clic derecho en el Escritorio → Nuevo → Acceso directo
    echo          - Programa : wscript.exe
    echo          - Argumentos: /nologo "%LAUNCHER_VBS%"
)

:FIN
:: -----------------------------------------------
:: INSTALACION COMPLETADA
:: -----------------------------------------------
color 0A
echo.
echo  ======================================================
echo       INSTALACION COMPLETADA
echo  ======================================================
echo.
echo   FitPro esta corriendo en Docker.
echo.
echo   Acceso:
echo     Web  : http://localhost
echo     API  : http://localhost/api/v1
echo.
echo   Uso diario:
echo     Doble clic en "FitPro" en tu Escritorio
echo.
echo   Para detener:
echo     Ejecuta detener_programa.bat
echo.
echo  ======================================================
echo.
color 0F
pause
endlocal