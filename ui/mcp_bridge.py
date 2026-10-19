"""User-only local named pipe. MCP stdio proxy forwards into Qt's main-thread runtime."""
import json
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtNetwork import QLocalServer
from core.mcp_contract import pipe_name, self_tools


class SelfMCPBridge(QObject):
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._connected)
        self.available = self.server.listen(pipe_name())
        self.clients = set()

    def _connected(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.clients.add(socket)
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._release(s))
            QTimer.singleShot(10000, lambda s=socket: s.abort() if s in self.clients else None)

    def _release(self, socket):
        self.clients.discard(socket)
        socket.deleteLater()

    def _read(self, socket):
        if socket.bytesAvailable() > 100000:
            socket.abort()
            return
        if not socket.canReadLine():
            return
        try:
            request = json.loads(bytes(socket.readLine()).decode('utf-8'))
            name, args = request['name'], request.get('arguments', {})
            if name not in {t['name'] for t in self_tools()} or not isinstance(args, dict):
                raise ValueError('未知工具或参数类型无效')
            panel = self.pet._ensure_agent_panel()
            result = panel.runtime.execute(name, args)
            if name != 'app_state':
                panel.store.append(panel.active_id, 'tool', 'MCP 外部调用：' + name + '\n' + json.dumps(args, ensure_ascii=False))
                panel.render()
            response = dict(ok=True, result=result)
        except Exception as exc:
            response = dict(ok=False, error=str(exc))
        socket.write((json.dumps(response, ensure_ascii=False) + '\n').encode('utf-8'))
        socket.flush()
        socket.disconnectFromServer()

    def close(self):
        for socket in list(self.clients):
            socket.abort()
        self.server.close()
