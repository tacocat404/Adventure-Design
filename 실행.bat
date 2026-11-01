@echo off
chcp 65001 >nul
rem 쿠션톡 한 번에 켜기: 주방(백엔드)과 홀(프론트) 창이 따로 뜨고 브라우저가 열려요.
cd /d "%~dp0"

if not exist "backend\.venv" (
  echo [처음 한 번] 백엔드 설치 중...
  python -m venv backend\.venv || goto :fail
  backend\.venv\Scripts\python -m pip install -q -r backend\requirements.txt || goto :fail
)
if not exist "frontend\node_modules" (
  echo [처음 한 번] 프론트 설치 중...
  pushd frontend && call npm install && popd || goto :fail
)

start "쿠션톡 주방 (백엔드) - 끄지 마세요" /d "%~dp0backend" cmd /k ".venv\Scripts\python -m uvicorn app.api.main:app --reload"
start "쿠션톡 홀 (프론트) - 끄지 마세요" /d "%~dp0frontend" cmd /k "npm run dev"
echo 서버를 켜는 중이에요. 잠시 뒤 브라우저가 열려요.
timeout /t 5 >nul
start "" http://localhost:5173
exit /b

:fail
echo 설치에 실패했어요. Python 3.12와 Node.js가 깔려 있는지 확인해 주세요.
pause
