"""Windows observation/input tools. No per-application allowlist in full access mode."""
import base64
import ctypes
from ctypes import wintypes
import io
import threading
import time
import uuid


class ComputerControl:
    def __init__(self, access=None):
        from core.desktop_access import DesktopAccess
        self.access=access or DesktopAccess()
        self.observation=None

    def execute(self,args,cancel=None):
        # Match screenshot and input coordinates on mixed-DPI monitors without
        # changing Qt's UI-thread coordinate system.
        user=ctypes.windll.user32
        setter=getattr(user,'SetThreadDpiAwarenessContext',None)
        previous=None
        if setter:
            setter.restype=ctypes.c_void_p;setter.argtypes=[ctypes.c_void_p]
            previous=setter(ctypes.c_void_p(-4))
        try:return self._execute(args,cancel)
        finally:
            if setter and previous:setter(previous)

    def _execute(self,args,cancel=None):
        if not self.access.enabled:raise ValueError('屏幕与输入需要开启完整访问')
        cancel=cancel or threading.Event()
        if cancel.is_set():raise RuntimeError('已停止屏幕操作')
        import win32gui
        action=args.get('action')
        if action=='windows':
            windows=[]
            def collect(hwnd,_):
                title=win32gui.GetWindowText(hwnd)
                if title and win32gui.IsWindowVisible(hwnd):
                    windows.append(dict(hwnd=hwnd,title=title,rect=win32gui.GetWindowRect(hwnd)))
            win32gui.EnumWindows(collect,None)
            return dict(windows=windows[:100])
        if action=='focus':
            hwnd=int(args['hwnd'])
            if not win32gui.IsWindow(hwnd):raise ValueError('窗口已关闭，请重新列出')
            win32gui.ShowWindow(hwnd,9);win32gui.SetForegroundWindow(hwnd)
            self.observation=None
            return dict(focused=win32gui.GetForegroundWindow()==hwnd,needs_observe=True)
        if action=='observe':
            from PIL import ImageGrab
            hwnd=int(args.get('hwnd') or win32gui.GetForegroundWindow())
            if hwnd!=win32gui.GetForegroundWindow():raise ValueError('先 focus 目标窗口再观察，避免遮挡误认')
            rect=win32gui.GetWindowRect(hwnd)
            if rect[2]<=rect[0] or rect[3]<=rect[1]:raise ValueError('窗口没有可见区域')
            frame=ImageGrab.grab(bbox=rect,all_screens=True).convert('RGB')
            frame.thumbnail((1600,1200))
            output=io.BytesIO();frame.save(output,format='JPEG',quality=78)
            token=uuid.uuid4().hex
            self.observation=dict(id=token,hwnd=hwnd,rect=rect,time=time.monotonic())
            return dict(observation_id=token,hwnd=hwnd,title=win32gui.GetWindowText(hwnd),
                desktop_rect=rect,image_size=frame.size,
                coordinates='鼠标坐标为桌面物理像素；截图坐标需按 desktop_rect/image_size 换算',
                _image_url='data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode())
        if action=='accessibility':
            hwnd=int(args.get('hwnd') or win32gui.GetForegroundWindow())
            if not win32gui.IsWindow(hwnd):raise ValueError('窗口已关闭')
            script='''Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$rootElement=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]HWND_VALUE)
$nodes=$rootElement.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$items=for($i=0;$i -lt [Math]::Min($nodes.Count,150);$i++) {
  try {$c=$nodes.Item($i).Current; if($c.Name -or $c.AutomationId) {
    [pscustomobject]@{name=$c.Name;id=$c.AutomationId;type=$c.ControlType.ProgrammaticName;enabled=$c.IsEnabled;bounds=$c.BoundingRectangle.ToString()}
  }} catch {}
}
ConvertTo-Json -InputObject @($items) -Compress -Depth 3'''.replace('HWND_VALUE',str(hwnd))
            from core.desktop_access import ROOT
            return self.access.run(script,str(ROOT),6,cancel)
        observed=self.observation
        if not observed or args.get('observation_id')!=observed['id'] or time.monotonic()-observed['time']>30:
            raise ValueError('观察已过期；先 observe 再输入')
        if win32gui.GetForegroundWindow()!=observed['hwnd'] or win32gui.GetWindowRect(observed['hwnd'])!=observed['rect']:
            self.observation=None
            raise ValueError('前台窗口或位置已改变，先重新观察')
        self.observation=None
        def position(x,y):
            x,y=int(x),int(y);left,top,right,bottom=observed['rect']
            if not left<=x<right or not top<=y<bottom:raise ValueError('输入坐标超出刚才观察的窗口')
            ctypes.windll.user32.SetCursorPos(x,y)
        user=ctypes.windll.user32
        if action in ('click','double_click','move','drag'):
            position(args['x'],args['y'])
            if action in ('click','double_click'):
                down,up=(8,16) if args.get('button')=='right' else (2,4)
                for _ in range(2 if action=='double_click' else 1):
                    user.mouse_event(down,0,0,0,0);user.mouse_event(up,0,0,0,0)
            elif action=='drag':
                # Validate destination before holding the button.
                end_x,end_y=int(args['end_x']),int(args['end_y'])
                l,t,r,b=observed['rect']
                if not l<=end_x<r or not t<=end_y<b:raise ValueError('拖动目标超出窗口')
                user.mouse_event(2,0,0,0,0)
                try:
                    for step in range(1,13):
                        if cancel.wait(.02):raise RuntimeError('拖动已取消')
                        position(args['x']+(end_x-args['x'])*step/12,args['y']+(end_y-args['y'])*step/12)
                finally:user.mouse_event(4,0,0,0,0)
        elif action=='scroll':
            delta=int(args.get('delta',-3))
            if not -20<=delta<=20:raise ValueError('滚动量需要-20到20')
            user.mouse_event(0x800,0,0,delta*120,0)
        elif action=='hotkey':
            keys=str(args.get('keys','')).lower().split('+')
            codes={'ctrl':17,'alt':18,'shift':16,'win':91,'enter':13,'tab':9,'esc':27,'backspace':8,'delete':46,
                'up':38,'down':40,'left':37,'right':39,'home':36,'end':35,'space':32}
            values=[codes[k] if k in codes else ord(k.upper()) if len(k)==1 and k.isascii() else 111+int(k[1:]) if k.startswith('f') and k[1:].isdigit() and 1<=int(k[1:])<=12 else 0 for k in keys]
            if not values or len(values)>5 or 0 in values:raise ValueError('不支持的组合键')
            try:
                for code in values:user.keybd_event(code,0,0,0)
            finally:
                for code in reversed(values):user.keybd_event(code,0,2,0)
        elif action=='type':
            text=str(args.get('text',''))
            if len(text)>4000:raise ValueError('单次输入最多4000字')
            # KEYEVENTF_UNICODE; preserves the user's clipboard.
            class KI(ctypes.Structure):
                _fields_=[('vk',wintypes.WORD),('scan',wintypes.WORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class MI(ctypes.Structure):
                _fields_=[('dx',wintypes.LONG),('dy',wintypes.LONG),('data',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class U(ctypes.Union):_fields_=[('ki',KI),('mi',MI)]
            class INPUT(ctypes.Structure):_fields_=[('type',wintypes.DWORD),('value',U)]
            encoded=text.encode('utf-16-le')
            for offset in range(0,len(encoded),2):
                if cancel.is_set():raise RuntimeError('文字输入已取消')
                scan=int.from_bytes(encoded[offset:offset+2],'little')
                inputs=(INPUT*2)(INPUT(1,U(ki=KI(0,scan,4,0,0))),INPUT(1,U(ki=KI(0,scan,6,0,0))))
                if user.SendInput(2,inputs,ctypes.sizeof(INPUT))!=2:raise RuntimeError('Windows 拒绝输入；检查实际进程权限')
        else:raise ValueError('未知屏幕操作')
        return dict(input_sent=True,action=action,needs_observe=True,message='输入已发送；必须重新观察验证效果')
