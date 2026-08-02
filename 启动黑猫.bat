@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

title 黑猫桌宠启动器

REM ========== 检测 Python ==========
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo ========================================
        echo  [错误] 未找到 Python！
        echo ========================================
        echo.
        echo  请先安装 Python 3.8+：
        echo    1. 访问 https://www.python.org/downloads/
        echo    2. 下载 Windows installer (64-bit)
        echo    3. 安装时务必勾选 "Add Python to PATH"
        echo    4. 安装完成后重新运行此脚本
        echo.
        pause
        exit /b 1
    ) else (
        set "PYTHON=py"
        set "PYTHONW=pyw"
    )
) else (
    set "PYTHON=python"
    where pythonw >nul 2>&1
    if errorlevel 1 (set "PYTHONW=python") else (set "PYTHONW=pythonw")
)

echo [1/3] Python 环境检测中...
%PYTHON% --version 2>nul
if errorlevel 1 (
    echo [错误] Python 无法正常运行
    pause
    exit /b 1
)

REM ========== 检测/安装依赖 ==========
echo [2/3] 检查依赖包...
%PYTHON% -c "import PyQt5; import edge_tts" 2>nul
if errorlevel 1 (
    echo [提示] 首次启动正在安装依赖包，请稍候...
    echo.
    %PYTHON% -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [提示] 镜像源失败，尝试官方源...
        %PYTHON% -m pip install -r requirements.txt
        if errorlevel 1 (
            echo.
            echo ========================================
            echo  [错误] 依赖安装失败！
            echo ========================================
            echo  请检查网络连接后重试，或手动执行：
            echo    pip install PyQt5 edge-tts Pillow pywin32 requests
            echo.
            pause
            exit /b 1
        )
    )
    echo [OK] 依赖安装完成！
) else (
    echo [OK] 依赖已就绪
)

REM ========== 启动桌宠 ==========
echo [3/3] 启动黑猫桌宠...
echo.
echo  提示：右键点击桌宠可打开菜单，双击可互动。
echo  黑猫已在桌面右下角出现～
echo.

REM 用 pythonw 启动（无控制台窗口）
start "" %PYTHONW% main.py

REM 等待 2 秒检查进程是否存活
timeout /t 2 /nobreak >nul 2>&1
%PYTHON% -c "import subprocess,sys; p=subprocess.run(['tasklist','/FI','IMAGENAME eq pythonw.exe','/NH'],capture_output=True,text=True); sys.exit(0 if 'pythonw' in p.stdout.lower() else 1)" 2>nul

exit
