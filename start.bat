@echo off
chcp 65001 >nul
echo ========================================
echo   TDX 选股系统启动脚本
echo ========================================
echo.

REM 设置 Go 编译环境
set CGO_ENABLED=1
set MINGW_BIN=C:\Users\baiyl3\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin
set PATH=%MINGW_BIN%;%PATH%

cd /d "%~dp0"

echo [1/3] 编译 Go 服务...
cd web
go build -o server.exe .
if %errorlevel% neq 0 (
    echo Go 编译失败！
    pause
    exit /b 1
)
echo Go 编译成功
cd ..

echo.
echo [2/3] 启动 Go 服务（端口 18080）...
start "TDX-Go-Server" cmd /k "cd /d %~dp0web && server.exe"

timeout /t 3 /nobreak >nul

echo.
echo [3/3] 启动 Python 策略服务（端口 18081）...
start "TDX-Python-Strategy" cmd /k "cd /d %~dp0strategy && python main.py"

echo.
echo ========================================
echo   启动完成！
echo   Go 服务:     http://localhost:18080
echo   Python 服务: http://localhost:18081
echo   前端页面:    http://localhost:18080
echo ========================================
echo.
pause
