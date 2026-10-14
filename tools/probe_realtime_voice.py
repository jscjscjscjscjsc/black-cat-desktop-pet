"""One bounded live API probe. No microphone capture; no retries or model fallback."""
import base64
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.realtime_voice import load_settings, connection_url, session_settings
import websocket


def probe():
    cfg = load_settings()
    if not cfg.get('free_only') or cfg.get('free_quota_confirmed_model') != cfg.get('model') or \
            cfg.get('free_quota_confirmed_provider') != cfg.get('provider'):
        raise ValueError('Free quota protection has not been confirmed for this platform/model')
    started = time.monotonic()
    deadline = started + 45
    ws = websocket.create_connection(connection_url(cfg),
                                     header=['Authorization: Bearer ' + cfg['api_key'].strip()], timeout=12)
    metrics = dict(provider=cfg['provider'], model=cfg['model'],
                   session_configured=False, audio_bytes=0, completed=False)
    try:
        ws.settimeout(2)
        requested = False
        transcript = ''
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise ConnectionError('Remote connection closed before completion')
            event = json.loads(raw)
            kind = event.get('type')
            if kind == 'error':
                code = str(event.get('error', {}).get('code', 'unknown'))
                raise ValueError('API error code: ' + code)
            if kind == 'session.created':
                ws.send(json.dumps(dict(type='session.update', session=session_settings(cfg)), ensure_ascii=False))
            elif kind == 'session.updated' and not requested:
                metrics['session_configured'] = True
                ws.send(json.dumps(dict(type='conversation.item.create', item=dict(
                    id='item_' + uuid.uuid4().hex, type='message', role='user',
                    content=[dict(type='input_text', text='这是连接测试。请只说一句：咕嘎，饲养员，本鹅已经准备好聊天啦。')]
                )), ensure_ascii=False))
                ws.send(json.dumps(dict(type='response.create')))
                requested = True
            elif kind == 'response.audio.delta':
                if not metrics['audio_bytes']:
                    metrics['first_audio_seconds'] = round(time.monotonic() - started, 2)
                metrics['audio_bytes'] += len(base64.b64decode(event.get('delta', ''), validate=True))
            elif kind == 'response.audio_transcript.done':
                transcript = event.get('transcript', '')
            elif kind == 'response.done':
                metrics['response_status'] = event.get('response', {}).get('status')
                if metrics['response_status'] == 'failed':
                    metrics['failure_code'] = event.get('response', {}).get('status_details', {}).get('error', {}).get('code')
                metrics['completed'] = metrics['response_status'] == 'completed' and metrics['audio_bytes'] > 0
                metrics['audio_seconds'] = round(metrics['audio_bytes'] / 48000, 2)
                metrics['transcript_present'] = bool(transcript)
                metrics['elapsed_seconds'] = round(time.monotonic() - started, 2)
                print(json.dumps(metrics, ensure_ascii=False), flush=True)
                Path('realtime_validation.log').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
                return 0 if metrics['completed'] else 1
        raise TimeoutError('Live probe exceeded 45 seconds; stopped')
    finally:
        ws.close(timeout=1)


if __name__ == '__main__':
    try:
        sys.exit(probe())
    except Exception as exc:
        # Never dump headers, token, server response or raw handshake exception.
        status = getattr(exc, 'status_code', None)
        safe = str(exc) if isinstance(exc, (ValueError, TimeoutError)) else type(exc).__name__
        print(json.dumps({'probe_failed': safe, 'http_status': status}, ensure_ascii=False), flush=True)
        sys.exit(1)
