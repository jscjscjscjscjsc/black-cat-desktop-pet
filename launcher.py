# -*- coding: utf-8 -*-
"""黑猫桌宠守护启动器 — 由 启动黑猫.bat 用 pythonw 调用

作用：
- 以 __main__ 方式运行 main.py（等价于 python main.py）
- 任何启动异常：写入 startup.log，并弹窗显示错误（不再无声消失）
- 正常运行则本进程就是桌宠进程（无多余进程）
"""
import os
import sys
import io
import json
import traceback
import ctypes
import runpy

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ROOT, 'startup.log')

# 官方 Qt 目录（aqt 安装的 Qt 5.15.2；wheel 自带的 Qt 与本机 Win11 24H2 不兼容）
# 存在时优先加载官方 Qt DLL 和插件，解决 "no Qt platform plugin" 错误
QT_DIR = os.path.join(os.environ.get('USERPROFILE', ''),
                      '.zcode', 'tools', 'qt', '5.15.2', 'msvc2019_64')


def _prepare_qt():
    """在导入 PyQt5 之前：优先加载官方 Qt 的 DLL 与插件路径"""
    qt_bin = os.path.join(QT_DIR, 'bin')
    qt_plugins = os.path.join(QT_DIR, 'plugins')
    if os.path.isdir(qt_bin):
        try:
            os.add_dll_directory(qt_bin)
        except Exception:
            pass
    if os.path.isdir(qt_plugins):
        os.environ['QT_PLUGIN_PATH'] = qt_plugins
        platforms = os.path.join(qt_plugins, 'platforms')
        if os.path.isdir(platforms):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = platforms
        mediaservice = os.path.join(qt_plugins, 'mediaservice')
        if os.path.isdir(mediaservice):
            os.environ['QT_MEDIA_BACKEND'] = 'windows'
    return os.path.isdir(qt_bin)


def _show_error(text):
    try:
        ctypes.windll.user32.MessageBoxW(None, text, '黑猫桌宠 - 启动失败', 0x10)
    except Exception:
        pass


def main():
    # 把输出重定向到 startup.log（pythonw 默认无控制台）
    try:
        logf = open(LOG_PATH, 'w', encoding='utf-8')
        sys.stdout = io.TextIOWrapper(logf, encoding='utf-8')
        sys.stderr = sys.stdout
    except Exception:
        pass

    def excepthook(tp, val, tb):
        text = ''.join(traceback.format_exception(tp, val, tb))
        try:
            sys.stderr.write(text)
            sys.stderr.flush()
        except Exception:
            pass
        _show_error('桌宠启动时发生错误：\n\n' + text[-2000:])

    sys.excepthook = excepthook

    # 管理员模式：一键拔线需要管理员权限（ai_config.json 的 run_as_admin）
    # UAC 被拒绝时降级为普通模式继续运行
    try:
        with open(os.path.join(ROOT, 'ai_config.json'), 'r', encoding='utf-8') as _f:
            _cfg = json.load(_f)
        if _cfg.get('run_as_admin'):
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                ctypes.windll.shell32.ShellExecuteW(
                    None, 'runas', sys.executable,
                    f'"{os.path.join(ROOT, "launcher.py")}"', ROOT, 1)
                sys.exit(0)
    except Exception:
        pass

    # 优先加载官方 Qt（修复平台插件初始化失败）
    if _prepare_qt():
        try:
            sys.stderr.write('[launcher] 使用官方 Qt 5.15.2\n')
            sys.stderr.flush()
        except Exception:
            pass

    try:
        # 等价于 python main.py
        runpy.run_path(os.path.join(ROOT, 'main.py'), run_name='__main__')
    except SystemExit:
        pass
    except Exception:
        excepthook(*sys.exc_info())
        sys.exit(1)


if __name__ == '__main__':
    main()
