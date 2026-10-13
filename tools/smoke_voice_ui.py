"""Finite offscreen desktop integration smoke; no external APIs or microphone."""
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from ui.pet_window import PetWindow
from ui.voice_dialog import VoiceCallDialog
from core.realtime_voice import RealtimeVoice

app = QApplication([])
with patch('core.keyboard_hook.KeyboardHook.start'), patch('ui.tts_engine.TTSEngine.speak'):
    pet = PetWindow()
    engine = RealtimeVoice(pet)
    pet._realtime_voice = engine
    panel = VoiceCallDialog(engine, pet)
    pet._voice_call_panel = panel
    panel.show()
    panel._append('饲养员', '我想连续聊一会儿。')
    panel._append('咕嘎', '咕嘎，饲养员，本鹅在听呢。')
    panel.status.setText('离线界面验证 · 麦克风未开启')
    def finish():
        assert pet._tray.contextMenu().actions()[2].text() == '🎙 持续语音对话（阿里）'
        assert '连续聊' in panel.transcript.toPlainText()
        for timer in pet.findChildren(QTimer):
            timer.stop()
        panel.close()
        pet._anim.stop()
        pet._status.stop()
        pet._tray.hide()
        print('Desktop + call panel + tray actions: PASS', flush=True)
        app.quit()
    QTimer.singleShot(150, finish)
    app.exec_()
