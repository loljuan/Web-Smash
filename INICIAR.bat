@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Chara Maker - Smash Ultimate

rem ---- Buscar Python (preferimos 3.12, que es el mas compatible con rembg) ----
set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

rem ---- Crear el entorno la primera vez ----
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  Preparando Chara Maker por primera vez. Tardara unos minutos...
  echo.
  %PY% -m venv .venv || goto error
)

rem ---- Instalar o actualizar dependencias si requirements.txt ha cambiado ----
fc /b requirements.txt ".venv\requirements.txt" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto error
  copy /y requirements.txt ".venv\requirements.txt" >nul
)

".venv\Scripts\python.exe" chara.py app
pause
exit /b 0

:nopython
echo.
echo  No encuentro Python 3.10 - 3.13 en este ordenador.
echo  Instala Python 3.12 desde la pagina que se va a abrir y, en el instalador,
echo  marca la casilla "Add python.exe to PATH". Despues vuelve a abrir INICIAR.bat
echo.
start "" https://www.python.org/downloads/release/python-3129/
pause
exit /b 1

:error
echo.
echo  Algo ha fallado al instalar. Revisa la conexion a internet y vuelve a abrir INICIAR.bat
echo  Si sigue fallando, borra la carpeta .venv y prueba otra vez.
pause
exit /b 1
