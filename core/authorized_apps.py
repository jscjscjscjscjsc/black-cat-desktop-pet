"""Only user-selected application paths can be launched; model text is never a command."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AuthorizedApps:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / 'runtime/chat/authorized_apps.json')

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
        entries = self.entries()
        if name not in entries:
            raise ValueError('此软件未授权。请在“软件权限”里添加，然后再让我打开')
        target = Path(entries[name])
        if not target.is_file():
            raise ValueError('已授权的软件路径已失效，请重新选择')
        os.startfile(str(target))
        return dict(name=name, launch_requested=True,
                    message='Windows 已接受启动请求；这不代表已经取得软件内部操作权限')
