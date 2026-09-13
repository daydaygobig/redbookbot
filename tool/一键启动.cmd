@echo off
cd /d %~dp0
title 有词儿念念控制台服务（保持运行，可最小化）

rem 已在运行则直接打开网页
curl -s -o nul -m 2 http://127.0.0.1:8932/api/config
if not errorlevel 1 (
  start "" http://127.0.0.1:8932/
  exit
)

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Python，请先安装 Python 3 并勾选 Add to PATH：
  echo        https://www.python.org/downloads/
  pause
  exit /b
)

rem 后台最小化启动服务，等 2 秒后打开控制台
start "redbookbot-console" /min cmd /c "cd /d %~dp0 && python config_server.py"
ping -n 3 127.0.0.1 >nul
start "" http://127.0.0.1:8932/
echo 控制台已在浏览器打开。此窗口可以关闭。
ping -n 4 127.0.0.1 >nul
