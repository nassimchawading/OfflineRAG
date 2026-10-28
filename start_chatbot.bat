@echo off
rem Starts the OfflineRAG chatbot: Ollama (own minimized window) + the Streamlit app (this window).
rem Double-click it, or run it from PowerShell: .\start_chatbot.bat
rem To stop: close this window (or Ctrl+C), then close the "Ollama - OfflineRAG" window.

rem Work from the folder of this file, wherever the project was copied.
cd /d "%~dp0"
title OfflineRAG - chatbot

rem Python: the project venv, else the portable Python (share kit without .venv).
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=tools\python312\python.exe"
if not exist "%PY%" (
    echo [ERREUR] Python introuvable: ni .venv\Scripts\python.exe ni tools\python312\python.exe
    pause
    exit /b 1
)

rem App already running? Then only open the browser.
curl.exe -s -o nul http://localhost:8501/_stcore/health && (
    echo L'application tourne deja: ouverture du navigateur.
    start "" http://localhost:8501
    exit /b 0
)

rem 1. Ollama: start it only if it is not already running.
curl.exe -s -o nul http://127.0.0.1:11434/api/version && goto ollama_ok
echo Demarrage d'Ollama (fenetre reduite "Ollama - OfflineRAG")...
start "Ollama - OfflineRAG" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ollama.ps1"

set /a tries=0
:wait_ollama
curl.exe -s -o nul http://127.0.0.1:11434/api/version && goto ollama_ok
set /a tries+=1
if %tries% geq 60 (
    echo [ERREUR] Ollama ne repond pas apres 60 s. Regardez la fenetre "Ollama - OfflineRAG".
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_ollama

:ollama_ok
echo Ollama est pret.

rem 2. Open the browser as soon as the app answers (small hidden helper, gives up after 2 min).
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://localhost:8501/_stcore/health | Out-Null; Start-Process 'http://localhost:8501'; break } catch { Start-Sleep 1 } }"

rem 3. The app (blocks until it is stopped).
echo Demarrage de l'application: http://localhost:8501  (Ctrl+C pour arreter)
"%PY%" -m streamlit run src\app.py

echo.
echo Application arretee. Fermez aussi la fenetre "Ollama - OfflineRAG" pour liberer le GPU.
pause
