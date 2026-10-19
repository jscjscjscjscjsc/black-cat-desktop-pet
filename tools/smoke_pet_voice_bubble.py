"""Real offscreen Qt: hidden voice, streaming bubble, click-to-reopen and end-call."""
import os
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));os.environ['QT_QPA_PLATFORM']='offscreen'
from launcher import _prepare_qt
_prepare_qt()
from PyQt5.QtCore import QSettings,QTimer,Qt,QPoint
from PyQt5.QtGui import QImage,QPainter,QColor,QFontDatabase
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest
from core.chat_workspace import ChatWorkspace
from core.realtime_agent import AgentRealtimeVoice
from core.realtime_voice import DEFAULTS
from ui.pet_window import PetWindow
from ui.agent_chat import AgentChatWindow

app=QApplication([])
for font in ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/msyhbd.ttc'):
    QFontDatabase.addApplicationFont(font)
with tempfile.TemporaryDirectory() as folder,patch('core.keyboard_hook.KeyboardHook.start'),patch('ui.tts_engine.TTSEngine.speak'):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,folder)
    pet=PetWindow()
    for timer in pet.findChildren(QTimer):timer.stop()
    panel=AgentChatWindow(pet,ChatWorkspace(Path(folder)/'chat.sqlite3'));pet._agent_panel=panel
    cfg=dict(DEFAULTS,api_key='offline-only')
    with patch('core.realtime_voice.load_settings',return_value=cfg),patch.object(AgentRealtimeVoice,'start') as start:
        pet._open_agent_voice();app.processEvents()
        voice=panel.voice;voice._cfg=cfg
        assert panel.voice_active and not panel.isVisible()
        assert pet._agent_bubble.isVisible()
        assert not voice._stop.is_set()
        ident=panel.active_id
        voice._handle_event(dict(type='response.created',response=dict(id='r1')))
        voice._handle_event(dict(type='response.audio_transcript.delta',response_id='r1',delta='好呀，我在这里陪你。'))
        voice._handle_event(dict(type='response.audio_transcript.delta',response_id='r1',delta='窗口收起来也能边聊边做事。'))
        app.processEvents()
        assert '边聊边做事' in pet._agent_bubble.full_text
        assert not panel.isVisible()
        before_text=pet._agent_bubble.full_text
        voice._cancelled.append('old-response')
        voice._handle_event(dict(type='response.audio_transcript.delta',response_id='old-response',delta='过期文字'))
        app.processEvents()
        assert pet._agent_bubble.full_text==before_text
        voice._handle_event(dict(type='response.audio_transcript.done',response_id='r1',transcript=pet._agent_bubble.full_text))
        QTest.mouseClick(pet._agent_bubble.text,Qt.LeftButton,pos=QPoint(10,10));app.processEvents()
        assert panel.isVisible() and panel.active_id==ident
        assert panel.voice is voice and panel.voice_active
        panel.hide_button.click();app.processEvents()
        assert not panel.isVisible() and not voice._stop.is_set()
        pet._show_agent_bubble('好呀，我在这里陪你。窗口收起来也能边聊边做事。',ident)
        pet._agent_bubble.set_speaking(True)
        before=pet._agent_bubble.pos();pet.move(pet.pos()+QPoint(40,20));app.processEvents()
        assert pet._agent_bubble.pos()!=before
        pet.move(0,0);app.processEvents()
        area=app.primaryScreen().availableGeometry()
        assert area.contains(pet._agent_bubble.frameGeometry())
        # Render app-owned widgets only; no desktop capture or microphone/API access.
        canvas=QImage(620,620,QImage.Format_ARGB32);canvas.fill(QColor('#edf0f7'))
        painter=QPainter(canvas)
        painter.drawPixmap((620-pet.width())//2,285,pet.grab())
        painter.drawPixmap((620-pet._agent_bubble.width())//2,85,pet._agent_bubble.grab())
        painter.end()
        output=ROOT/'runtime/chat/pet-voice-bubble-preview.png';output.parent.mkdir(parents=True,exist_ok=True)
        canvas.save(str(output))
        pet._agent_bubble.stop_button.click();app.processEvents()
        assert not panel.voice_active and voice._stop.is_set()
        assert not pet._agent_bubble.stop_button.isVisible()
        start.assert_called_once()
    # Exercise the actual worker dispatch with a real bounded command, offline model.
    from core.desktop_access import DesktopAccess
    access=DesktopAccess(Path(folder)/'local-access.json');access.set_enabled(True)
    panel.agent.config={'api_key':'offline-only'}
    replies=[dict(role='assistant',content=None,tool_calls=[dict(id='local1',type='function',function=dict(
        name='local_computer',arguments=json.dumps(dict(action='run',command="Write-Output 'BUBBLE_AGENT_OK'",cwd=folder,seconds=5))))]),
        dict(role='assistant',content='本机命令已经完成。')]
    with patch('core.desktop_access.DesktopAccess',return_value=access),patch.object(panel.agent,'_request',side_effect=lambda *a,**kw:replies.pop(0)):
        panel.send('运行一条本机验证命令。')
        deadline=time.monotonic()+8
        while panel.busy and time.monotonic()<deadline:
            app.processEvents();time.sleep(.01)
        if panel.busy:
            panel.agent.cancel()
            raise AssertionError('Local worker did not complete')
        assert 'BUBBLE_AGENT_OK' in str(panel.store.messages(panel.active_id))
        assert pet._agent_bubble.full_text=='本机命令已经完成。'
    pet._self_mcp.close();panel.shutdown();panel.hide();pet._agent_bubble.hide()
    pet._anim.stop();pet._status.stop();pet._tray.hide();pet.hide()
    print('PASS: hidden voice; streaming bubble; cancelled text ignored; same-chat reopen; positioning; stop; real local command via agent worker')
    print(str(output))
