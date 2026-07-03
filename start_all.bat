@echo off
echo [SYSTEM] Stopping existing processes...
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM node.exe /T >nul 2>&1

echo [SYSTEM] Starting Trading Bot Components...

:: Environment fixes for stability
set OPENBLAS_NUM_THREADS=1
set OPENBLAS_MAIN_FREE=1
set PYTHONUNBUFFERED=1

echo [1/3] MongoDB...
docker-compose up -d

echo [2/3] Prices (5000)...
cd backend
start "PriceAPI" cmd /k "npm start"

echo [3/3] Signals (8000)...
cd ..\signal-engine
:: Use 0.0.0.0 to listen on all interfaces
start "SignalEngine" cmd /k "venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

echo [DONE] Dashboard: http://localhost:5173
cd ..\frontend
start "Dashboard" cmd /k "npm run dev"
