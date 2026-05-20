' =============================================================
' execution/windows/lanzador_programa.vbs
' Lanzador silencioso de FitPro con Docker para Windows.
' Ejecuta completamente sin mostrar ventanas de CMD ni terminales.
' Proceso:
'   1. Calcula rutas absolutas desde la ubicacion del script
'   2. Verifica que Docker Desktop este instalado
'   3. Verifica que el motor de Docker este activo
'   4. Levanta los contenedores con docker compose up -d
'   5. Espera a que los servicios esten disponibles
'   6. Abre el navegador predeterminado en http://localhost
' =============================================================

Option Explicit

' -----------------------------------------------
' Declaracion de variables
' -----------------------------------------------
Dim fso, objShell
Dim scriptFullPath, scriptDir, execDir, projectRoot
Dim composeFile, envFile
Dim composeCmd, cmdDockerUp, cmdDockerCheck
Dim result, waitSeconds

' -----------------------------------------------
' Crear objetos COM necesarios
' -----------------------------------------------
Set fso      = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

' -----------------------------------------------
' Calcular rutas absolutas del proyecto
' Este script esta en: <raiz>/execution/windows/
' Se sube 2 niveles para obtener la raiz del proyecto
' -----------------------------------------------
scriptFullPath = WScript.ScriptFullName

' Nivel 1: execution/windows/ → execution/
scriptDir = fso.GetParentFolderName(scriptFullPath)

' Nivel 2: execution/ → raiz del proyecto
execDir     = fso.GetParentFolderName(scriptDir)
projectRoot = fso.GetParentFolderName(execDir)

' Rutas clave del proyecto
composeFile = projectRoot & "\docker-compose.yml"
envFile     = projectRoot & "\docker\.env"

' -----------------------------------------------
' Verificacion 1: docker-compose.yml debe existir
' Si no existe, el proyecto no esta en la ruta correcta
' -----------------------------------------------
If Not fso.FileExists(composeFile) Then
    MsgBox "No se encontro el archivo docker-compose.yml." & vbCrLf & vbCrLf & _
           "Ruta esperada:" & vbCrLf & composeFile & vbCrLf & vbCrLf & _
           "Verifica que el proyecto este completo y que el" & vbCrLf & _
           "lanzador este en la carpeta: execution\windows\", _
           vbCritical + vbOKOnly, "FitPro - Archivo No Encontrado"
    WScript.Quit 1
End If

' -----------------------------------------------
' Verificacion 2: docker/.env debe existir
' Sin el .env los contenedores no pueden iniciar correctamente
' -----------------------------------------------
If Not fso.FileExists(envFile) Then
    MsgBox "No se encontro el archivo de configuracion." & vbCrLf & vbCrLf & _
           "Ruta esperada:" & vbCrLf & envFile & vbCrLf & vbCrLf & _
           "Solucion: ejecuta primero Instalador_programa.bat" & vbCrLf & _
           "para crear la configuracion inicial.", _
           vbCritical + vbOKOnly, "FitPro - Configuracion Faltante"
    WScript.Quit 1
End If

' -----------------------------------------------
' Verificacion 3: Docker Desktop instalado y motor activo
' Ejecutar "docker info" con ventana oculta y capturar codigo de salida
' Si devuelve distinto de 0, Docker no esta corriendo
' -----------------------------------------------
result = objShell.Run("cmd /c docker info > nul 2>&1", 0, True)
If result <> 0 Then
    MsgBox "Docker Desktop no esta activo." & vbCrLf & vbCrLf & _
           "Para iniciar FitPro necesitas:" & vbCrLf & vbCrLf & _
           "1. Abre Docker Desktop desde el menu Inicio" & vbCrLf & _
           "2. Espera a que el icono de la ballena en la bandeja" & vbCrLf & _
           "   del sistema deje de parpadear (30-60 segundos)" & vbCrLf & _
           "3. Luego abre FitPro nuevamente", _
           vbExclamation + vbOKOnly, "FitPro - Docker No Esta Activo"
    WScript.Quit 1
End If

' -----------------------------------------------
' Detectar version de Docker Compose disponible
' V2 usa "docker compose" (plugin integrado en Docker Desktop)
' V1 usa "docker-compose" (herramienta separada, mas antigua)
' -----------------------------------------------
result = objShell.Run("cmd /c docker compose version > nul 2>&1", 0, True)
If result = 0 Then
    ' Compose V2 disponible (recomendado, incluido en Docker Desktop moderno)
    composeCmd = "docker compose"
Else
    result = objShell.Run("cmd /c docker-compose --version > nul 2>&1", 0, True)
    If result = 0 Then
        ' Compose V1 disponible (version antigua independiente)
        composeCmd = "docker-compose"
    Else
        MsgBox "Docker Compose no esta disponible." & vbCrLf & vbCrLf & _
               "Reinstala Docker Desktop para obtener Compose V2" & vbCrLf & _
               "incluido automaticamente.", _
               vbCritical + vbOKOnly, "FitPro - Docker Compose No Encontrado"
        WScript.Quit 1
    End If
End If

' -----------------------------------------------
' Levantar los contenedores Docker en segundo plano
' "up -d" inicia todos los servicios definidos en docker-compose.yml
' Se ejecuta desde la raiz del proyecto donde esta el docker-compose.yml
' Ventana completamente oculta (0) para experiencia limpia sin terminales
' Espera a que el comando termine (True) antes de continuar
' -----------------------------------------------
cmdDockerUp = "cmd /c cd /d """ & projectRoot & """ && " & composeCmd & " up -d"
result = objShell.Run(cmdDockerUp, 0, True)

If result <> 0 Then
    MsgBox "Ocurrio un error al iniciar los servicios de FitPro." & vbCrLf & vbCrLf & _
           "Para ver el detalle del error abre CMD y ejecuta:" & vbCrLf & _
           composeCmd & " logs" & vbCrLf & vbCrLf & _
           "Directorio del proyecto:" & vbCrLf & projectRoot, _
           vbCritical + vbOKOnly, "FitPro - Error al Iniciar"
    WScript.Quit 1
End If

' -----------------------------------------------
' Pausa de arranque interno
' Aunque los contenedores ya estan activos, los servicios
' internos (FastAPI, nginx, DB) necesitan unos segundos
' para inicializar completamente y comenzar a responder
' -----------------------------------------------
WScript.Sleep 6000

' -----------------------------------------------
' Abrir el navegador predeterminado del sistema
' Shell.Run con una URL HTTP la abre automaticamente
' en el navegador configurado como predeterminado en Windows
' WindowStyle 1 = ventana normal visible para el usuario
' -----------------------------------------------
objShell.Run "http://localhost", 1, False

' -----------------------------------------------
' Limpieza de objetos COM
' -----------------------------------------------
Set objShell = Nothing
Set fso      = Nothing

WScript.Quit 0