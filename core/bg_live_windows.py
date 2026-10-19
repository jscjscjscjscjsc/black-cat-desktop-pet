"""Desktop application's Windows input backend; does not run at import time."""
import os
from pathlib import Path
import time


class HearthstoneWindow:
    def __init__(self):
        import win32api
        import win32con
        import win32gui
        import win32process
        self.api,self.con,self.gui,self.process=win32api,win32con,win32gui,win32process

    def find(self):
        found=[]
        def visit(hwnd,_):
            if not self.gui.IsWindowVisible(hwnd):
                return
            _,pid=self.process.GetWindowThreadProcessId(hwnd)
            handle=None
            try:
                handle=self.api.OpenProcess(0x1000,False,pid)
                import ctypes
                length=ctypes.c_ulong(2048)
                text=ctypes.create_unicode_buffer(2048)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(int(handle),0,text,ctypes.byref(length)) and Path(text.value).name.lower()=='hearthstone.exe':
                    found.append(hwnd)
            except Exception:
                pass
            finally:
                if handle:
                    handle.Close()
        self.gui.EnumWindows(visit,None)
        if len(found)!=1:
            raise RuntimeError('请先打开炉石并完成登录；需要唯一游戏窗口')
        return found[0]

    def open(self):
        try:
            hwnd=self.find()
            self.gui.ShowWindow(hwnd,self.con.SW_RESTORE)
            self.gui.SetForegroundWindow(hwnd)
            return '已切回炉石；在主菜单中进入酒馆战棋后可执行'
        except RuntimeError:
            from core.log_reader import find_log_path
            path=find_log_path()
            launcher=Path(path).parents[2]/'Hearthstone Beta Launcher.exe' if path else None
            if not launcher or not launcher.is_file():
                raise RuntimeError('未找到本机炉石启动器，请先从战网打开一次')
            os.startfile(str(launcher))
            return '已打开炉石启动器；等待战网或游戏加载，登录由你完成'

    def cancelled(self):
        return bool(self.api.GetAsyncKeyState(self.con.VK_ESCAPE)&0x8000)

    def geometry(self,hwnd):
        left,top=self.gui.ClientToScreen(hwnd,(0,0))
        _,_,width,height=self.gui.GetClientRect(hwnd)
        if width<640 or height<400 or self.gui.IsIconic(hwnd):
            raise RuntimeError('游戏窗口太小或已最小化')
        return hwnd,left,top,width,height

    def capture(self):
        from PIL import ImageGrab
        hwnd=self.find()
        self.check_integrity(hwnd)
        self.gui.SetForegroundWindow(hwnd)
        time.sleep(.25)
        geometry=self.geometry(hwnd)
        _,left,top,width,height=geometry
        if self.gui.GetForegroundWindow()!=hwnd:
            raise RuntimeError('无法切到炉石窗口')
        return ImageGrab.grab(bbox=(left,top,left+width,top+height)),geometry

    def check_integrity(self,hwnd):
        import win32security
        _,pid=self.process.GetWindowThreadProcessId(hwnd)
        handle=self.api.OpenProcess(0x1000,False,pid)
        game_token=own_token=None
        try:
            game_token=win32security.OpenProcessToken(handle,8)
            own_token=win32security.OpenProcessToken(self.api.GetCurrentProcess(),8)
            game=win32security.GetTokenInformation(game_token,win32security.TokenElevation)
            own=win32security.GetTokenInformation(own_token,win32security.TokenElevation)
            if game and not own:
                raise RuntimeError('炉石以管理员运行；请手动以管理员启动咕嘎，或用普通权限重开炉石。当前未发送输入。')
        finally:
            if game_token:game_token.Close()
            if own_token:own_token.Close()
            handle.Close()

    def execute(self,grounding,action,geometry):
        from core.bg_live import validate_grounding
        validate_grounding(grounding,action)
        hwnd,left,top,width,height=geometry
        if self.find()!=hwnd or self.geometry(hwnd)!=geometry or self.gui.GetForegroundWindow()!=hwnd or self.cancelled():
            raise RuntimeError('窗口、焦点或停止状态已改变；未执行')
        def point(value):
            return left+round(value[0]*width),top+round(value[1]*height)
        source=point(grounding['source'])
        hit=self.gui.WindowFromPoint(source)
        if hit!=hwnd and self.gui.GetAncestor(hit,2)!=hwnd:
            raise RuntimeError('目标被其他窗口遮挡；未执行')
        self.api.SetCursorPos(source)
        self.api.mouse_event(self.con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
        try:
            if action['kind'] in ('BUY','SELL','PLAY'):
                target=point(grounding['destination'])
                for i in range(1,17):
                    if self.cancelled() or self.gui.GetForegroundWindow()!=hwnd:
                        raise RuntimeError('拖动中被停止；请查看当前局面')
                    self.api.SetCursorPos((round(source[0]+(target[0]-source[0])*i/16),
                                           round(source[1]+(target[1]-source[1])*i/16)))
                    time.sleep(.02)
            else:
                time.sleep(.05)
        finally:
            self.api.mouse_event(self.con.MOUSEEVENTF_LEFTUP,0,0,0,0)
