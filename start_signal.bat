@echo off
set OPENBLAS_NUM_THREADS=1
set OPENBLAS_MAIN_FREE=1
set PYTHONUNBUFFERED=1
cd /d "d:\treading bot\signal-engine"
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
