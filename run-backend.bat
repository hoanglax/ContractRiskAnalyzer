```bat
@echo off
cd /d "%~dp0"
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
pause
```