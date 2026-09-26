@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Chara Maker - Smash Ultimate

if exist ".venv\Scripts\python.exe" goto deps

echo.
echo  Preparando Chara Maker por primera vez. Tardara unos minutos...
echo.

rem ---- 1) Si ya tienes Python 3.10 - 3.14 instalado, se usa ese ----
set "PY="
for %%V in (3.12 3.13 3.11 3.14 3.10) do if not defined PY call :trypy %%V
if defined PY %PY% -m venv .venv
if exist ".venv\Scripts\python.exe" goto deps
if exist ".venv" rmdir /s /q ".venv"

rem ---- 2) Si no, se descarga uv, que instala su propio Python dentro de esta carpeta ----
echo  No he encontrado Python en el ordenador: descargo uno solo para este programa...
set "UV=%~dp0tools\uv\uv.exe"
if not exist "%UV%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; New-Item -ItemType Directory -Force 'tools\uv' | Out-Null; Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile 'tools\uv\uv.zip'; Expand-Archive -Force 'tools\uv\uv.zip' 'tools\uv'; Remove-Item 'tools\uv\uv.zip'; Get-ChildItem 'tools\uv' -Recurse -Filter uv.exe | Select-Object -First 1 | Move-Item -Destination 'tools\uv\uv.exe' -Force -ErrorAction SilentlyContinue"
)
if not exist "%UV%" goto error
set "UV_PYTHON_INSTALL_DIR=%~dp0tools\python"
if exist ".venv" rmdir /s /q ".venv"
"%UV%" venv .venv --python 3.12
if not exist ".venv\Scripts\python.exe" goto error

:deps
rem ---- Instalar o actualizar dependencias si requirements.txt ha cambiado ----
fc /b requirements.txt ".venv\requirements.txt" >nul 2>nul
if not errorlevel 1 goto run
echo.
echo  Instalando lo necesario (solo la primera vez o tras una actualizacion)...
echo.
if exist "tools\uv\uv.exe" goto deps_uv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
goto deps_done
:deps_uv
"tools\uv\uv.exe" pip install -r requirements.txt --python ".venv\Scripts\python.exe"
if errorlevel 1 goto error
:deps_done
copy /y requirements.txt ".venv\requirements.txt" >nul

:run
".venv\Scripts\python.exe" chara.py app
pause
exit /b 0

:trypy
py -%1 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -%1"
exit /b 0

:error
echo.
echo  Algo ha fallado al instalar. Revisa la conexion a internet y vuelve a abrir INICIAR.bat
echo  Si sigue fallando, borra las carpetas .venv y tools\uv y prueba otra vez,
echo  o copia el texto de esta ventana y pasaselo a Claude.
pause
exit /b 1
