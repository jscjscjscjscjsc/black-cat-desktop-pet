"""Explicit app grants, or discovered local apps when the user enables full access."""
import json
import os
from itertools import islice
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AuthorizedApps:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / 'runtime/chat/authorized_apps.json')
        from core.desktop_access import DesktopAccess
        self.access = DesktopAccess(self.path.parent/'local_access.json')

    def available(self, query=''):
        entries=dict(self.entries())
        if self.access.enabled:
            roots=[Path(os.environ.get('APPDATA',''))/'Microsoft/Windows/Start Menu/Programs',
                   Path(os.environ.get('PROGRAMDATA','C:/ProgramData'))/'Microsoft/Windows/Start Menu/Programs',
                   Path.home()/'Desktop']
            for index,root in enumerate(roots):
                if not root.is_dir():continue
                # Desktop contains user projects; never recursively walk those.
                paths=root.glob('*.lnk') if index==2 else root.rglob('*.lnk')
                for path in islice(paths,1000):
                    name=path.stem
                    if name in entries and entries[name]!=str(path):name+=' ['+path.parent.name+']'
                    entries.setdefault(name,str(path))
                    if len(entries)>=1000:break
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths') as registry:
                        for i in range(min(500,winreg.QueryInfoKey(registry)[0])):
                            name=winreg.EnumKey(registry,i)
                            try:
                                with winreg.OpenKey(registry,name) as key:
                                    target=os.path.expandvars(winreg.QueryValue(key,None)).strip('"')
                                    if Path(target).is_file():entries.setdefault(Path(name).stem,target)
                            except OSError:pass
                except OSError:pass
        query=str(query).strip().casefold()
        return {name:path for name,path in entries.items() if not query or query in name.casefold()}

    def entries(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}

    def _save(self, entries):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def grant(self, name, path):
        name = name.strip()
        target = Path(path).resolve(strict=True)
        if not name or len(name) > 80:
            raise ValueError('软件名称需要 1—80 个字符')
        if target.suffix.lower() not in ('.exe', '.lnk') or not target.is_file():
            raise ValueError('请选择软件 .exe 或快捷方式 .lnk')
        entries = self.entries()
        entries[name] = str(target)
        self._save(entries)

    def revoke(self, name):
        entries = self.entries()
        entries.pop(name, None)
        self._save(entries)

    def open(self, name):
        entries = self.available()
        if name not in entries:
            target=Path(name).expanduser()
            if not self.access.enabled or not target.is_absolute() or target.suffix.lower() not in ('.exe','.lnk'):
                raise ValueError('请先列出软件取得精确名称；完整访问模式也可传本机exe/lnk绝对路径')
        else:
            target = Path(entries[name])
        if not target.is_file():
            raise ValueError('已授权的软件路径已失效，请重新选择')
        os.startfile(str(target))
        return dict(name=name, launch_requested=True,
                    message='Windows 已接受启动请求；这不代表已经取得软件内部操作权限')
