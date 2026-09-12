@echo off
setlocal EnableExtensions
chcp 65001 >nul
title tociNoTool - Scene Release Suite
cd /d "%~dp0"
set "PYTHONUTF8=1"

REM Keep this file ASCII-only: it must work in legacy cmd.exe consoles too.

:menu
cls
echo.
echo  +======================================================================+
echo  ^|                       T O C I ( N O ) T O O L                       ^|
echo  ^|                     Scene ES Release Suite                          ^|
echo  ^|       Herramienta para la comunidad scene en espanol - jascott      ^|
echo  +======================================================================+
echo.
echo     [1]  Ejecutar tociNoTool
echo     [2]  Asistente de instalacion
echo.
echo     [Q]  Salir
echo.
set "OP="
set /p "OP= Selecciona una opcion: "
if not defined OP exit /b 0
if /i "%OP%"=="q" exit /b 0
if "%OP%"=="1" (
    set "ACCION=ejecutar"
    goto :asegurar_python
)
if "%OP%"=="2" (
    set "ACCION=asistente"
    goto :asegurar_python
)
echo.
echo  Opcion no valida.
pause
goto :menu

:asegurar_python
call :buscar_python
if defined PY goto :%ACCION%
cls
echo.
echo  +======================================================================+
echo  ^|                 ASISTENTE DE INSTALACION - PASO 1 DE 2              ^|
echo  +======================================================================+
echo.
echo  Para abrir el asistente se necesita Python 3.9 o superior.
echo  El asistente preparara despues el entorno aislado y las herramientas.
echo.
where winget >nul 2>&1 || goto :sin_winget
set "INSTALAR="
set /p "INSTALAR= Instalar Python 3.12 ahora con winget? [s/n]: "
if /i not "%INSTALAR%"=="s" goto :menu
winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    call :log_error "python-winget" "La instalacion automatica de Python ha fallado"
    goto :python_instalacion_fallo
)
call :buscar_python
if defined PY goto :asistente
echo.
echo  Python se ha instalado, pero esta ventana aun no lo detecta.
echo  Cierra el launcher y vuelve a abrirlo: el Asistente de instalacion se iniciara primero.
call :log_error "python-deteccion" "Python no se detecta despues de la instalacion"
pause
exit /b 1

:python_instalacion_fallo
echo.
echo  La instalacion automatica de Python no se ha completado.
echo  Puedes reintentar desde el launcher o instalarlo manualmente desde:
echo  https://www.python.org/downloads/
echo  Marca "Add python.exe to PATH" y vuelve a abrir el launcher.
pause
goto :menu

:sin_winget
echo  Instala Python 3.9 o superior desde https://www.python.org/downloads/
echo  Marca "Add python.exe to PATH" durante la instalacion y vuelve a abrir el launcher.
echo  El Asistente de instalacion continuara automaticamente antes de abrir la tool.
pause
goto :menu

:ejecutar
call :setup_listo
if errorlevel 1 goto :primera_ejecucion
%PY% -m tocinotool
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    call :log_error "ejecucion" "tociNoTool ha terminado con codigo %RC%"
    pause
)
goto :menu

:primera_ejecucion
cls
echo.
echo  Primera ejecucion detectada.
echo.
echo  Antes de usar tociNoTool debes ejecutar el Asistente de instalacion
echo  para preparar y comprobar las dependencias necesarias.
echo.
set "SETUP="
set /p "SETUP= [A] Iniciar asistente  [S] Salir: "
if /i "%SETUP%"=="a" goto :asistente
if /i "%SETUP%"=="s" goto :menu
echo  Elige A o S.
pause
goto :primera_ejecucion

:asistente
%PY% -m tocinotool --asistente-instalacion
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    call :log_error "asistente" "El asistente ha terminado con codigo %RC%"
    pause
)
goto :menu

:setup_listo
if not exist "%~dp0config\tool.yaml" exit /b 1
findstr /i /c:"completado: true" "%~dp0config\tool.yaml" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:buscar_python
set "PY="
where py >nul 2>&1 || goto :buscar_python_cmd
for %%V in (3.13 3.12 3.11 3.10 3.9) do (
    py -%%V -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=py -%%V" && goto :buscar_python_fin
)
:buscar_python_cmd
where python >nul 2>&1 || goto :buscar_python_fin
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=python"
:buscar_python_fin
exit /b

:log_error
REM Registro de respaldo para fallos anteriores a Python. ASCII por compatibilidad cmd.exe.
setlocal
set "PASO=%~1"
set "DETALLE=%~2"
set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "LOGFILE=%LOGDIR%\launcher_error_%RANDOM%_%RANDOM%.log"
(
    echo tociNoTool - informe de error del launcher
    echo Fecha: %DATE% %TIME%
    echo Version: 2.1.1
    echo Modulo: launcher
    echo Paso: %PASO%
    echo Detalle: %DETALLE%
    echo Sistema: %OS%
    echo Arquitectura: %PROCESSOR_ARCHITECTURE%
    echo Directorio tool: %~dp0
    where winget >nul 2>&1
    if errorlevel 1 (echo winget: no disponible) else (echo winget: disponible)
    where py >nul 2>&1
    if errorlevel 1 (echo Python launcher: no disponible) else (echo Python launcher: disponible)
) > "%LOGFILE%"
if exist "%LOGFILE%" echo  Informe de error: %LOGFILE%
endlocal
exit /b
