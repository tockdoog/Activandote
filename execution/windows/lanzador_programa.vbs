' =============================================================
' execution/windows/lanzador_programa.vbs
' Lanzador silencioso de FitPro con Docker para Windows.
' Ejecuta completamente sin mostrar ventanas de CMD ni terminales.
' Proceso:
'   1. Calcula rutas absolutas desde la ubicacion del script
'   2. Verifica que Docker Desktop este instalado
'   3. Verifica que el motor de Docker este activo
'   4. Detecta la IP de red local de Windows via WMI (para QR)
'   5. Escribe HOST_IP directamente en docker\.env (persistente)
'   6. Levanta los contenedores con docker compose up -d
'   7. Espera a que los servicios esten disponibles
'   8. Abre el navegador predeterminado en http://localhost
'
' NOTA IMPORTANTE (correccion del bug del QR):
' Anteriormente HOST_IP se inyectaba solo como variable de entorno
' efimera del proceso que ejecutaba "docker compose up". Eso fallaba
' si el usuario levantaba los contenedores de otra forma (por ejemplo
' con Instalador_programa.bat, que no seteaba esa variable), dejando
' HOST_IP vacia y forzando al backend a mostrar la IP interna de Docker
' en el QR (ej: 172.18.0.3). Ahora la IP se escribe directamente en
' docker\.env, que el backend siempre lee via env_file sin importar
' que script haya iniciado los contenedores.
' =============================================================

Option Explicit

' -----------------------------------------------
' Declaracion de variables principales
' -----------------------------------------------
Dim fso, objShell
Dim scriptFullPath, scriptDir, execDir, projectRoot
Dim composeFile, envFile
Dim composeCmd, cmdDockerUp
Dim result
Dim hostIP

' -----------------------------------------------
' Crear objetos COM necesarios
' -----------------------------------------------
Set fso      = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

' -----------------------------------------------
' Calcular rutas absolutas del proyecto.
' Este script esta en: <raiz>/execution/windows/
' Se sube 2 niveles para obtener la raiz del proyecto.
' -----------------------------------------------
scriptFullPath = WScript.ScriptFullName

' Nivel 1: execution/windows/ hacia execution/
scriptDir = fso.GetParentFolderName(scriptFullPath)

' Nivel 2: execution/ hacia raiz del proyecto
execDir     = fso.GetParentFolderName(scriptDir)
projectRoot = fso.GetParentFolderName(execDir)

' Rutas clave del proyecto
composeFile = projectRoot & "\docker-compose.yml"
envFile     = projectRoot & "\docker\.env"

' -----------------------------------------------
' Verificacion 1: docker-compose.yml debe existir.
' Sin este archivo el proyecto no esta en la ruta correcta.
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
' Verificacion 2: docker/.env debe existir.
' Sin el .env los contenedores no pueden iniciar correctamente.
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
' Verificacion 3: Docker Desktop instalado y motor activo.
' "docker info" retorna 0 solo si el motor esta corriendo.
' -----------------------------------------------
result = objShell.Run("cmd /c docker info > nul 2>&1", 0, True)
If result <> 0 Then
    MsgBox "Docker Desktop no esta activo." & vbCrLf & vbCrLf & _
           "Para iniciar FitPro necesitas:" & vbCrLf & vbCrLf & _
           "1. Abre Docker Desktop desde el menu Inicio" & vbCrLf & _
           "2. Espera a que el icono de la ballena deje de parpadear" & vbCrLf & _
           "   (30-60 segundos aproximadamente)" & vbCrLf & _
           "3. Luego abre FitPro nuevamente", _
           vbExclamation + vbOKOnly, "FitPro - Docker No Esta Activo"
    WScript.Quit 1
End If

' -----------------------------------------------
' Detectar version de Docker Compose disponible.
' V2: "docker compose" — incluido en Docker Desktop moderno
' V1: "docker-compose" — herramienta separada, version antigua
' -----------------------------------------------
result = objShell.Run("cmd /c docker compose version > nul 2>&1", 0, True)
If result = 0 Then
    composeCmd = "docker compose"
Else
    result = objShell.Run("cmd /c docker-compose --version > nul 2>&1", 0, True)
    If result = 0 Then
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
' Detectar IP de red local de Windows para el codigo QR.
' Se llama a la funcion que usa WMI sin GoTo (compatible VBScript).
' -----------------------------------------------
hostIP = ObtenerIPRedLocal()

' -----------------------------------------------
' Escribir la IP detectada directamente en docker\.env.
' Esto reemplaza la inyeccion via variable de entorno del proceso:
' el archivo .env es leido siempre por docker-compose (env_file),
' sin importar que comando o script haya iniciado los contenedores.
' Si no se detecto IP valida, se limpia la linea HOST_IP= para que
' el backend caiga a su fallback controlado (nunca a una IP vieja
' de otra red que ya no aplica).
' -----------------------------------------------
ActualizarHostIPEnEnv envFile, hostIP

' -----------------------------------------------
' Levantar contenedores. El backend leera HOST_IP desde docker\.env
' automaticamente gracias a "env_file" en docker-compose.yml.
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
' Pausa de arranque: los servicios internos (FastAPI, nginx, DB)
' necesitan unos segundos para inicializar y responder peticiones.
' -----------------------------------------------
WScript.Sleep 6000

' -----------------------------------------------
' Abrir navegador predeterminado en http://localhost.
' WindowStyle 1 = ventana normal visible para el usuario.
' -----------------------------------------------
objShell.Run "http://localhost", 1, False

' -----------------------------------------------
' Limpieza de objetos COM
' -----------------------------------------------
Set objShell = Nothing
Set fso      = Nothing

WScript.Quit 0


' =============================================================
' FUNCION: ActualizarHostIPEnEnv
' Escribe (o reemplaza) la linea "HOST_IP=..." dentro del archivo
' docker\.env indicado. Si la linea ya existe, se reemplaza; si no
' existe, se agrega al final. Si ip llega vacio, escribe "HOST_IP="
' para limpiar cualquier valor obsoleto de una red anterior.
' =============================================================
Sub ActualizarHostIPEnEnv(ByVal rutaEnvFile, ByVal ip)
    Dim fsoLocal, ts, contenido, lineas, i, encontrado, nuevoContenido, lineaLimpia

    Set fsoLocal = CreateObject("Scripting.FileSystemObject")
    If Not fsoLocal.FileExists(rutaEnvFile) Then Exit Sub

    ' Leer todo el contenido actual del archivo .env
    Set ts = fsoLocal.OpenTextFile(rutaEnvFile, 1) ' 1 = ForReading
    contenido = ts.ReadAll
    ts.Close

    lineas = Split(contenido, vbLf)
    encontrado = False

    For i = 0 To UBound(lineas)
        lineaLimpia = Replace(lineas(i), vbCr, "")
        If Left(lineaLimpia, 8) = "HOST_IP=" Then
            lineas(i) = "HOST_IP=" & ip
            encontrado = True
        End If
    Next

    nuevoContenido = Join(lineas, vbLf)

    If Not encontrado Then
        nuevoContenido = nuevoContenido & vbLf & "HOST_IP=" & ip
    End If

    ' Sobreescribir el archivo completo con el contenido actualizado
    Set ts = fsoLocal.OpenTextFile(rutaEnvFile, 2, True) ' 2 = ForWriting
    ts.Write nuevoContenido
    ts.Close

    Set fsoLocal = Nothing
End Sub


' =============================================================
' FUNCION: ObtenerIPRedLocal
' Detecta la IP real de Windows en la red local usando WMI.
'
' Reescrita SIN GoTo para evitar "Expected statement" en VBScript.
' VBScript no permite GoTo para saltar fuera de bloques For...Next,
' por lo que se usan variables de control de flujo en su lugar.
'
' Prioridad de seleccion:
'   1. Redes privadas clase C: 192.168.x.x  (WiFi domestico/oficina)
'   2. Redes privadas clase A: 10.x.x.x     (empresarial/VPN)
'
' Descartadas automaticamente:
'   - 127.x.x.x   loopback localhost
'   - 172.x.x.x   red interna Docker/WSL2
'   - 169.254.x.x  APIPA sin conexion real
'   - IPv6         contienen ":" y no sirven para QR HTTP
' =============================================================
Function ObtenerIPRedLocal()
    Dim objWMI, colAdaptadores, objAdaptador
    Dim ip, i
    Dim ipPreferida, ipAlternativa
    Dim encontrado, esInvalida

    ObtenerIPRedLocal = ""
    ipPreferida   = ""
    ipAlternativa = ""
    encontrado    = False

    On Error Resume Next

    ' Conectar al proveedor WMI del sistema local
    Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
    If Err.Number <> 0 Then
        On Error GoTo 0
        Exit Function
    End If

    ' Consultar adaptadores de red activos con IP asignada
    Set colAdaptadores = objWMI.ExecQuery( _
        "SELECT IPAddress FROM Win32_NetworkAdapterConfiguration WHERE IPEnabled = True")

    If Err.Number <> 0 Then
        On Error GoTo 0
        Exit Function
    End If

    ' Recorrer cada adaptador de red disponible
    For Each objAdaptador In colAdaptadores
        ' Solo procesar si el adaptador tiene IPs asignadas y no encontramos preferida
        If Not IsNull(objAdaptador.IPAddress) And Not encontrado Then
            For i = 0 To UBound(objAdaptador.IPAddress)
                ip = Trim(objAdaptador.IPAddress(i))

                ' Marcar como invalida y evaluar cada condicion de descarte
                esInvalida = False

                ' Descartar IPv6: contienen dos puntos
                If InStr(ip, ":") > 0 Then esInvalida = True

                ' Descartar loopback 127.x.x.x
                If Left(ip, 4) = "127." Then esInvalida = True

                ' Descartar red interna Docker y WSL2 172.x.x.x
                If Left(ip, 4) = "172." Then esInvalida = True

                ' Descartar APIPA 169.254.x.x (sin red real)
                If Left(ip, 8) = "169.254." Then esInvalida = True

                ' Descartar IPs vacias o sin formato valido
                If ip = "" Then esInvalida = True
                If InStr(ip, ".") = 0 Then esInvalida = True

                ' Solo procesar IPs validas que no hayan sido descartadas
                If Not esInvalida Then

                    ' PRIORIDAD 1: Red WiFi/Ethernet domestica 192.168.x.x
                    ' Al encontrarla se detiene la busqueda inmediatamente
                    If Left(ip, 8) = "192.168." Then
                        ipPreferida = ip
                        encontrado  = True  ' Detiene el bucle externo tambien

                    ' PRIORIDAD 2: Red empresarial o VPN 10.x.x.x
                    ' Solo se guarda si no hay ya una alternativa guardada
                    ElseIf Left(ip, 3) = "10." Then
                        If ipAlternativa = "" Then
                            ipAlternativa = ip
                        End If
                    End If

                End If

            Next ' siguiente IP del adaptador
        End If
    Next ' siguiente adaptador

    On Error GoTo 0

    ' Retornar la mejor IP segun prioridad encontrada
    If ipPreferida <> "" Then
        ObtenerIPRedLocal = ipPreferida
    ElseIf ipAlternativa <> "" Then
        ObtenerIPRedLocal = ipAlternativa
    End If
End Function