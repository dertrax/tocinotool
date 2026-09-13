<#
Genera una actualización diferencial para una edición Windows de tociNoTool.

Uso:
  .\herramientas\generar_actualizacion.ps1 `
    -Base .\publicar\tociNoTool-v2.1.3-windows `
    -Nuevo .\publicar\tociNoTool-v2.1.4-windows `
    -Version 2.1.4

El resultado contiene dos archivos que se copian JUNTOS a la raíz de la tool
instalada: el ZIP y Actualizar-tociNoTool-vX.Y.Z.bat. No incorpora config/,
.venv/ ni logs/, por lo que los ajustes y datos locales del usuario permanecen
intactos.
#>
[CmdletBinding()]
param(
    [string] $Base,
    [Parameter(Mandatory)] [string] $Nuevo,
    [Parameter(Mandatory)] [string] $Version,
    [string] $BaseVersion,
    [switch] $Acumulativa,
    [string] $Destino = (Join-Path $PSScriptRoot ("..\\publicar\\actualizacion-v{0}" -f $Version))
)

$ErrorActionPreference = 'Stop'
$nuevoPath = (Resolve-Path -LiteralPath $Nuevo).Path
if (-not $Acumulativa -and [string]::IsNullOrWhiteSpace($Base)) {
    throw 'Indica -Base para una actualización diferencial o usa -Acumulativa con -BaseVersion.'
}
if ($Acumulativa -and [string]::IsNullOrWhiteSpace($BaseVersion)) {
    throw 'Una actualización acumulativa requiere -BaseVersion, por ejemplo 2.1.0.'
}
if (-not $Acumulativa) {
    $basePath = (Resolve-Path -LiteralPath $Base).Path
    if ($basePath -eq $nuevoPath) {
        throw 'Base y Nuevo deben ser carpetas de versiones distintas.'
    }
}

function Ruta-Relativa([string] $raiz, [string] $ruta) {
    return $ruta.Substring($raiz.Length).TrimStart([char]'\', [char]'/') -replace '\\', '/'
}

# La configuración es particular de cada usuario. Los demás archivos se
# comparan por hash, incluido binaries/ si en una versión futura cambian.
function Es-Privado([string] $relativa) {
    return $relativa -match '^(config|\.venv|logs)(/|$)' -or
           $relativa -match '(^|/)(__pycache__|_legacy)(/|$)' -or
           $relativa -match '\.py[co]$'
}

$baseHashes = @{}
if (-not $Acumulativa) {
    Get-ChildItem -LiteralPath $basePath -File -Recurse | ForEach-Object {
        $rel = Ruta-Relativa $basePath $_.FullName
        if (-not (Es-Privado $rel)) { $baseHashes[$rel] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    }
}

if (Test-Path -LiteralPath $Destino) {
    throw "El destino ya existe: $Destino. Elige otro o revisa su contenido; no se sobrescribe una actualización previa."
}
$payload = Join-Path $Destino 'payload'
New-Item -ItemType Directory -Path $payload -Force | Out-Null
$cambios = [System.Collections.Generic.List[string]]::new()

Get-ChildItem -LiteralPath $nuevoPath -File -Recurse | ForEach-Object {
    $rel = Ruta-Relativa $nuevoPath $_.FullName
    # La acumulativa actualiza el código desde una versión antigua sin obligar
    # a descargar de nuevo los binarios portables. Para renovar binarios se
    # publica un paquete completo o una actualización diferencial con Base.
    if (-not (Es-Privado $rel) -and (-not $Acumulativa -or $rel -notmatch '^binaries/')) {
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        if ($Acumulativa -or -not $baseHashes.ContainsKey($rel) -or $baseHashes[$rel] -ne $hash) {
            $destinoFichero = Join-Path $payload ($rel -replace '/', '\\')
            New-Item -ItemType Directory -Path (Split-Path -Parent $destinoFichero) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destinoFichero -Force
            $cambios.Add($rel)
        }
    }
}

if ($cambios.Count -eq 0) { throw 'No hay ficheros públicos modificados entre ambas versiones.' }

$baseVersion = if ($Acumulativa) { $BaseVersion } elseif ((Split-Path -Leaf $basePath) -match 'v(.+)-windows$') { $Matches[1] } else { 'anterior' }
$ramaCompatible = $BaseVersion -replace '\.\d+$', ''
if ($Acumulativa) {
    # Una acumulativa lleva todas las plantillas/código desde su base. No debe
    # alarmar a quien ya tenga una revisión intermedia de la misma rama.
    $mensajeCompatibilidad = "Esta actualizacion acumulativa es compatible con versiones $ramaCompatible.x desde $BaseVersion."
    $comprobacionVersion = "findstr /C:`"__version__ = `" `"%CD%\tocinotool\__init__.py`" | findstr /C:`"$ramaCompatible.`" >nul"
    $avisoVersion = "No se ha detectado una version $ramaCompatible.x. Revisa que el ZIP corresponda a tu instalacion antes de continuar."
} else {
    $mensajeCompatibilidad = "Esta actualizacion esta preparada para la version $baseVersion."
    $comprobacionVersion = "findstr /C:`"__version__ = `" `"%CD%\tocinotool\__init__.py`" | findstr /C:`"$baseVersion`" >nul"
    $avisoVersion = "No se ha detectado exactamente la version $baseVersion. Revisa que el ZIP corresponda a tu instalacion antes de continuar."
}
$zipNombre = "tociNoTool-update-v$Version.zip"
$batNombre = "Actualizar-tociNoTool-v$Version.bat"
$zip = Join-Path $Destino $zipNombre
Compress-Archive -Path $payload -DestinationPath $zip -CompressionLevel Optimal -Force
Remove-Item -LiteralPath $payload -Recurse -Force

$lista = ($cambios | Sort-Object | ForEach-Object { "echo   - $_" }) -join "`r`n"
$bat = @"
@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title tociNoTool - Actualizacion v$Version
cd /d "%~dp0"

set "ZIP=%CD%\$zipNombre"
set "TEMP_DIR=%TEMP%\tociNoTool-update-v$Version-%RANDOM%%RANDOM%"

cls
echo.
echo  ================================================================
echo                    tociNoTool - Actualizacion v$Version
echo  ================================================================
echo.
echo  $mensajeCompatibilidad
echo  Mantendra intactos config, .venv, logs y tus datos del tracker.
echo.
echo  Se actualizaran estos archivos:
$lista
echo.

if not exist "%ZIP%" (
  echo  ERROR: falta %ZIP%.
  echo  Copia este BAT y el ZIP juntos en la raiz de tociNoTool.
  goto :fin
)
if not exist "%CD%\tocinotool\__init__.py" (
  echo  ERROR: esta carpeta no parece una instalacion de tociNoTool.
  goto :fin
)
$comprobacionVersion
if errorlevel 1 (
  echo  AVISO: $avisoVersion
)
echo.
set /p "CONFIRMAR=Aplicar actualizacion? [S/N]: "
if /I not "%CONFIRMAR%"=="S" goto :cancelado

mkdir "%TEMP_DIR%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%TEMP_DIR%' -Force"
if errorlevel 1 (
  echo  ERROR: no se pudo abrir el ZIP. No se ha actualizado nada.
  rd /s /q "%TEMP_DIR%" >nul 2>&1
  goto :fin
)

robocopy "%TEMP_DIR%\payload" "%CD%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo  ERROR: no se pudieron copiar todos los archivos. Cierra la tool y reintenta.
  rd /s /q "%TEMP_DIR%" >nul 2>&1
  goto :fin
)
rd /s /q "%TEMP_DIR%" >nul 2>&1
del /q "%ZIP%" >nul 2>&1
echo.
echo  Actualizacion v$Version completada.
echo  El ZIP se ha eliminado. Este BAT ya no es necesario y puedes borrarlo.
goto :fin

:cancelado
echo.
echo  Actualizacion cancelada. No se ha cambiado ningun archivo.

:fin
echo.
if not defined TOCI_UPDATE_NO_PAUSE pause
endlocal
"@

[System.IO.File]::WriteAllText((Join-Path $Destino $batNombre), $bat, [System.Text.UTF8Encoding]::new($false))

$hashZip = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
Write-Host "Actualización creada: $Destino"
Write-Host "Base: $baseVersion  ->  Nueva: $Version"
Write-Host "Ficheros: $($cambios.Count)"
$cambios | Sort-Object | ForEach-Object { Write-Host "  $_" }
Write-Host "SHA-256 ZIP: $hashZip"
