@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到虚拟环境，请先运行：
  echo   py -m venv .venv
  echo   .venv\Scripts\pip install -r backend\requirements.txt
  pause
  exit /b 1
)
echo 正在启动 AI 期末复习整合包：http://127.0.0.1:8000
start "" http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
