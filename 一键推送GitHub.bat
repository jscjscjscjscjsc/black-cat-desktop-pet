@echo off
chcp 65001 >nul
title 咕嘎桌宠 - 推送到 GitHub
setlocal

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "GH=%USERPROFILE%\tools\gh\bin\gh.exe"
set "PATH=%USERPROFILE%\tools\gh\bin;%PATH%"
cd /d "C:\Users\Admin（无密码）\.zcode\workspace\default\guga-penguin-pet"

echo ============================================================
echo   咕嘎桌宠 - 推送到 GitHub
echo ============================================================
echo.
echo 步骤 1: GitHub 设备码登录 (会显示一个代码)
echo   - 浏览器打开 https://github.com/login/device
echo   - 输入显示的代码
echo   - 登录并授权
echo.

"%PY%" gh_login.py
if errorlevel 1 (
    echo [错误] 登录失败
    pause
    exit /b 1
)

echo.
echo 步骤 2: 配置 gh CLI 凭据
"%GH%" auth login --with-token < "%USERPROFILE%\.gh_token.txt"
"%GH%" auth status

echo.
echo 步骤 3: 配置 git 远程
git remote remove origin 2>nul
git remote add origin https://github.com/jscjscjscjscjsc/black-cat-desktop-pet.git

echo.
echo 步骤 4: 强制推送 (覆盖旧的黑猫桌宠内容)
git push -u origin main --force
if errorlevel 1 (
    echo [错误] 推送失败
    echo 如果仓库不存在, 先去 github.com 创建 black-cat-desktop-pet 仓库
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   推送成功! 访问:
echo   https://github.com/jscjscjscjscjsc/black-cat-desktop-pet
echo ============================================================
pause
