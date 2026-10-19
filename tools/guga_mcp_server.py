"""MCP stdio entrypoint. stdout contains protocol messages only; start the pet separately."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtNetwork import QLocalSocket
from core.mcp_contract import pipe_name, self_tools

VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')


def invoke(name, arguments):
    socket = QLocalSocket()
    socket.connectToServer(pipe_name())
    if not socket.waitForConnected(2000):
        return dict(ok=False, error='咕嘎尚未运行，请先启动桌宠')
    try:
        socket.write((json.dumps(dict(name=name, arguments=arguments), ensure_ascii=False) + '\n').encode('utf-8'))
        socket.flush()
        socket.waitForBytesWritten(2000)
        if not socket.canReadLine() and not socket.waitForReadyRead(8000):
            return dict(ok=False, error='咕嘎主界面响应超时')
        return json.loads(bytes(socket.readAll()).decode('utf-8'))
    finally:
        socket.abort()


def serve():
    app = QCoreApplication([])
    initialized = False
    negotiated = False
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Invalid request')
            if 'id' not in request:
                if request.get('method') == 'notifications/initialized' and negotiated:
                    initialized = True
                continue
            method = request.get('method')
            params = request.get('params') or {}
            if method == 'initialize':
                version = params.get('protocolVersion')
                negotiated = True
                result = dict(protocolVersion=version if version in VERSIONS else VERSIONS[0],
                    capabilities=dict(tools={}), serverInfo=dict(name='guga-self', version='2.0.0'))
            elif method == 'ping':
                result = {}
            elif not initialized:
                raise ValueError('Initialize first')
            elif method == 'tools/list':
                result = dict(tools=self_tools())
            elif method == 'tools/call':
                names = {t['name'] for t in self_tools()}
                if params.get('name') not in names:
                    raise ValueError('Unknown tool')
                value = invoke(params['name'], params.get('arguments', {}))
                result = dict(content=[dict(type='text', text=json.dumps(value, ensure_ascii=False))],
                              isError=not value.get('ok', False))
            else:
                response = dict(jsonrpc='2.0', id=request['id'], error=dict(code=-32601, message='Method not found'))
                print(json.dumps(response), flush=True)
                continue
            response = dict(jsonrpc='2.0', id=request['id'], result=result)
        except Exception as exc:
            response = dict(jsonrpc='2.0', id=request.get('id') if isinstance(request, dict) else None,
                            error=dict(code=-32602 if request is not None else -32700, message=str(exc)))
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    serve()
