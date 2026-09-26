@echo off
rem Atajo de la linea de comandos (para usarlo tu o otro Claude):  chara.bat crear foto.png --fighter mario
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta primero INICIAR.bat una vez para instalar el programa.
  exit /b 1
)
".venv\Scripts\python.exe" chara.py %*
