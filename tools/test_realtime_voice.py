"""Offline behavioral checks: no external APIs, audio capture or user credentials."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtWidgets import QApplication
from core.realtime_voice import DEFAULTS, PCMBuffer, RealtimeVoice, connection_url, session_settings
from ui.voice_dialog import VoiceSettingsDialog, VoiceCallDialog

APP = QApplication.instance() or QApplication([])
CFG = dict(DEFAULTS, workspace_id='test-space', api_key='test-credential', headphones=True,
           free_quota_confirmed_model=DEFAULTS['model'])


class Stream:
    opened = []
    def __init__(self, **kw):
        self.kw = kw
    def __enter__(self):
        self.opened.append(self)
        return self
    def __exit__(self, *args):
        self.opened.remove(self)


class Socket:
    def __init__(self):
        self.events = [dict(type='session.created'), dict(type='session.updated')]
        self.sent = []
        self.closed = threading.Event()
    def recv(self):
        if self.events:
            return json.dumps(self.events.pop(0))
        if self.closed.wait(0.02):
            return ''
        import websocket
        raise websocket.WebSocketTimeoutException()
    def send(self, message):
        self.sent.append(json.loads(message))
    def settimeout(self, timeout):
        pass
    def shutdown(self):
        self.closed.set()
    def close(self, **kwargs):
        self.closed.set()


class VoiceTests(unittest.TestCase):
    def test_region_and_key_validation(self):
        self.assertIn('test-space.cn-beijing.maas.aliyuncs.com', connection_url(CFG))
        for changed in [dict(workspace_id='../../evil'), dict(region='elsewhere'), dict(api_key='')]:
            with self.assertRaises(ValueError):
                connection_url(dict(CFG, **changed))

    def test_bounded_pcm_and_zero_padding(self):
        buf = PCMBuffer(8)
        buf.append(b'abcd')
        self.assertEqual(buf.read(6), (b'abcd\0\0', True))
        with self.assertRaises(BufferError):
            buf.append(b'012345678')
        self.assertFalse(buf)

    def test_capture_gating_mute_and_queue_limit(self):
        engine = RealtimeVoice()
        engine._cfg = dict(CFG, headphones=False)
        engine._generating = True
        engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.get_nowait(), bytes(4))
        engine._cfg['headphones'] = True
        engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.get_nowait(), b'abcd')
        engine.mute(True)
        for i in range(100):
            engine._capture(b'abcd', 2, None, None)
        self.assertEqual(engine._input.qsize(), 30)
        self.assertEqual(engine._input.get_nowait(), bytes(4))

    def test_cancelled_audio_never_returns(self):
        engine = RealtimeVoice()
        engine._handle_event(dict(type='response.created', response={'id':'old'}))
        data = base64.b64encode(b'1234').decode()
        engine._handle_event(dict(type='response.audio.delta', response_id='old', delta=data))
        self.assertTrue(engine._pcm)
        engine.interrupt()
        engine._handle_event(dict(type='response.audio.delta', response_id='old', delta=data))
        self.assertFalse(engine._pcm)
        engine._handle_event(dict(type='response.created', response={'id':'new'}))
        engine._handle_event(dict(type='response.audio.delta', response_id='new', delta=data))
        engine._handle_event(dict(type='response.done', response={'id':'old'}))
        self.assertTrue(engine._pcm)
        self.assertTrue(engine._generating)

    def test_context_is_bounded_and_not_persisted(self):
        settings = session_settings(CFG, [('饲养员', 'x'*2000)]*150)
        self.assertLess(len(settings['instructions']), 17000)
        self.assertEqual(settings['turn_detection']['type'], 'smart_turn')

    def test_unconfirmed_free_quota_blocks_network(self):
        engine = RealtimeVoice()
        with patch('websocket.create_connection') as connect:
            engine.start(dict(CFG, free_quota_confirmed_model=''))
            self.assertFalse(engine.active)
            connect.assert_not_called()

    def test_exhausted_free_quota_is_fatal(self):
        engine = RealtimeVoice()
        with self.assertRaisesRegex(ValueError, '免费额度'):
            engine._handle_event(dict(type='error', error={'code':'AllocationQuota.FreeTierOnly'}))

    def test_stop_releases_both_devices(self):
        engine = RealtimeVoice()
        socket = Socket()
        with patch('websocket.create_connection', return_value=socket), \
             patch('sounddevice.RawInputStream', Stream), patch('sounddevice.RawOutputStream', Stream):
            engine.start(CFG)
            deadline = time.monotonic() + 2
            while len(Stream.opened) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(Stream.opened), 2)
            engine.stop()
            engine._thread.join(3)
            self.assertFalse(engine.active)
            self.assertFalse(Stream.opened)
            self.assertTrue(socket.closed.is_set())

    def test_server_rejects_config_before_microphone_opens(self):
        engine = RealtimeVoice()
        socket = Socket()
        socket.events[1] = dict(type='error', error={'code':'invalid_parameter'})
        with patch('websocket.create_connection', return_value=socket), \
             patch('sounddevice.RawInputStream', Stream), patch('sounddevice.RawOutputStream', Stream):
            engine.start(CFG)
            engine._thread.join(3)
            self.assertFalse(engine.active)
            self.assertFalse(Stream.opened)
            self.assertIn('invalid_parameter', engine.last_error)

    def test_settings_preserve_existing_config_and_mask_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ai_config.json'
            path.write_text(json.dumps({'api_key':'old-chat-key','unrelated':42,'realtime_voice':CFG}), encoding='utf-8')
            with patch('ui.voice_dialog.CONFIG_PATH', path):
                dialog = VoiceSettingsDialog()
                self.assertEqual(dialog.key.echoMode(), dialog.key.Password)
                dialog._save()
                saved = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['api_key'], 'old-chat-key')
                self.assertEqual(saved['unrelated'], 42)
                self.assertEqual(saved['realtime_voice']['workspace_id'], 'test-space')
                dialog.deleteLater()

    def test_call_window_close_stops_capture(self):
        engine = RealtimeVoice()
        dialog = VoiceCallDialog(engine)
        dialog.show()
        dialog.close()
        self.assertTrue(engine._stop.is_set())
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
