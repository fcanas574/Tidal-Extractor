@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=C:\Users\Diego\AppData\Local\Programs\Python\Python314\python.exe"

if not exist "%PYTHON%" (
  echo Could not find Python at "%PYTHON%".
  echo Update start-app.bat to point at a working Python install.
  exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
  echo Frontend dependencies are missing. Run npm install in frontend first.
  exit /b 1
)

start "TidalExtractor API" cmd /k "cd /d "%ROOT%" && "%PYTHON%" -m uvicorn backend.main:app --reload --port 8000"
start "TidalExtractor Web" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo Started backend on http://127.0.0.1:8000
echo Started frontend on http://localhost:3000
echo.
echo Close the two windows that open to stop the app.
