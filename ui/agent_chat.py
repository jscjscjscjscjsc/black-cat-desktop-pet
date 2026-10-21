"""Guga's floating workspace: projects, durable chats, voice and observable self-control."""
import html
import json
import time

from PyQt5.QtCore import Qt, QEvent, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (QDialog, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTextBrowser, QPlainTextEdit, QInputDialog, QMenu,
    QSplitter, QCheckBox, QMessageBox)

from core.chat_workspace import ChatWorkspace
from core.self_agent import SelfAgent, ToolBridge
from core.realtime_agent import AgentRealtimeVoice
from ui.agent_runtime import AppRuntime


class AgentChatWindow(QDialog):
    def __init__(self, pet, store=None):
        super().__init__(pet, Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.pet = pet
        self.store = store or ChatWorkspace()
        self.active_id = None
        self.busy = False
        self.voice_active = False
        self.voice = None
        self._voice_task = None
        self._voice_readback = False
        self.show_archived = False
        self.expanded_logs = set()
        self.runtime = AppRuntime(pet, self, self.store)
        self.bridge = ToolBridge(self.runtime.execute, self)
        self.agent = SelfAgent(self.bridge, self)
        self.agent.completed.connect(self._completed)
        self.agent.activity.connect(self._activity)
        self.agent.progress.connect(self._task_progress)
        self._last_task_notice=0
        self._task_summary='正在规划第一步，尚未修改目标文件'
        self._task_started=0
        self._task_feedback_sequence=0
        self._task_heartbeat_timer=QTimer(self)
        self._task_heartbeat_timer.setInterval(1000)
        self._task_heartbeat_timer.timeout.connect(self._task_heartbeat)
        self.setWindowTitle('咕嘎 · 智能体')
        self.resize(960, 720)
        self.setMinimumSize(740, 540)
        self.setFont(QFont('Microsoft YaHei UI', 10))
        self.setObjectName('AgentWindow')
        self.setStyleSheet('''
            QDialog#AgentWindow { background: #ffffff; color: #252b37; }
            QWidget { color: #252b37; }
            QFrame#Sidebar { background: #f5f6f8; border-right: 1px solid #eceef1; }
            QLabel#Brand { font-size: 25px; font-weight: 700; }
            QLabel#Title { font-size: 18px; font-weight: 600; }
            QLabel#Muted { color: #8a909c; font-size: 11px; }
            QLabel#Badge { color: #38816c; background: #edf7f1; border-radius: 9px; padding: 5px 10px; }
            QPushButton { background: #fff; border: 1px solid #e4e7ed; border-radius: 9px;
                padding: 8px 12px; color: #454b58; }
            QPushButton:hover { background: #eceff5; }
            QPushButton:disabled { color: #adb2bc; background: #f6f7f9; }
            QPushButton#Primary { background: #4969ec; color: white; border: none; }
            QPushButton#Primary:hover { background: #3b56cf; }
            QPushButton:checked { background: #e7edff; border-color: #8399f2; color: #3f5bd2; }
            QTreeWidget { background: transparent; border: none; outline: none; font-size: 13px; }
            QTreeWidget::item { padding: 9px 3px; border-radius: 7px; }
            QTreeWidget::item:selected { background: #e6eaf4; color: #253b79; }
            QTreeWidget::item:hover { background: #eceef3; }
            QTextBrowser { border: none; background: #fff; font-size: 14px; }
            QPlainTextEdit { background: #f7f8fb; border: 1px solid #e5e8ef; border-radius: 12px;
                padding: 10px; font-size: 14px; selection-background-color: #cbd6ff; }
            QSplitter::handle { background: #eceef1; width: 1px; }
            QCheckBox { color: #858c98; font-size: 11px; }
            QMenu { background: white; border: 1px solid #e4e7ed; padding: 5px; }
            QMenu::item { padding: 8px 20px; }
            QMenu::item:selected { background: #edf1ff; }
        ''')
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter()
        outer.addWidget(splitter)
        sidebar = QFrame()
        sidebar.setObjectName('Sidebar')
        sidebar.setMinimumWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 24, 16, 18)
        brand = QLabel('咕嘎')
        brand.setObjectName('Brand')
        side.addWidget(brand)
        subtitle = QLabel('你的桌面伙伴，也能动手帮忙')
        subtitle.setObjectName('Muted')
        side.addWidget(subtitle)
        side.addSpacing(16)
        self.new_button = QPushButton('＋  新对话')
        self.new_button.clicked.connect(self.new_conversation)
        side.addWidget(self.new_button)
        self.project_button = QPushButton('新建项目')
        self.project_button.clicked.connect(self.new_project)
        side.addWidget(self.project_button)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(13)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemClicked.connect(self._selected)
        self.tree.itemDoubleClicked.connect(self._rename_item)
        side.addWidget(self.tree, 1)
        self.archive_button = QPushButton('已归档对话')
        self.archive_button.clicked.connect(self._toggle_archive)
        side.addWidget(self.archive_button)
        note = QLabel('项目与对话保存在这台电脑\n右键条目可更名、移动和归档')
        note.setObjectName('Muted')
        note.setWordWrap(True)
        side.addWidget(note)
        splitter.addWidget(sidebar)

        body = QFrame()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 22, 28, 18)
        header = QHBoxLayout()
        self.title = QLabel('新对话')
        self.title.setObjectName('Title')
        header.addWidget(self.title, 1)
        permissions = QPushButton('软件权限')
        permissions.clicked.connect(self.open_permissions)
        header.addWidget(permissions)
        rename = QPushButton('更名')
        rename.clicked.connect(self.rename_active)
        header.addWidget(rename)
        self.pin = QPushButton('置顶')
        self.pin.setCheckable(True)
        self.pin.setChecked(True)
        self.pin.toggled.connect(self._pin)
        header.addWidget(self.pin)
        self.hide_button = QPushButton('收起到咕嘎')
        self.hide_button.setToolTip('隐藏对话窗，保留通话和后台任务；点击咕嘎气泡可展开')
        self.hide_button.clicked.connect(self.hide_to_pet)
        header.addWidget(self.hide_button)
        self.close_button = QPushButton('关闭')
        self.close_button.setObjectName('CloseChat')
        self.close_button.setToolTip('关闭对话窗并结束语音；桌宠继续运行')
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.model_label = QLabel(str(self.agent.config.get('model', '未配置模型')) + ' 负责问答与任务 · 阿里端到端语音通话')
        self.model_label.setObjectName('Muted')
        layout.addWidget(self.model_label)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.anchorClicked.connect(self._log_link)
        layout.addWidget(self.view, 1)
        self.status = QLabel('●  就绪')
        self.status.setObjectName('Badge')
        layout.addWidget(self.status)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText('和咕嘎说话，或让它动手…\n例如：把自己移到右下角，再建一个“学习”项目')
        self.editor.setFixedHeight(102)
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor)
        controls = QHBoxLayout()
        self.voice_button = QPushButton('语音对话')
        self.voice_button.setCheckable(True)
        self.voice_button.toggled.connect(self.toggle_voice)
        controls.addWidget(self.voice_button)
        self.voice_settings_button = QPushButton('语音设置')
        self.voice_settings_button.clicked.connect(self.open_voice_settings)
        controls.addWidget(self.voice_settings_button)
        self.mute_button = QPushButton('静音')
        self.mute_button.setCheckable(True)
        self.mute_button.setEnabled(False)
        self.mute_button.toggled.connect(lambda checked: self.voice.mute(checked) if self.voice_active and self.voice else None)
        controls.addWidget(self.mute_button)
        self.interrupt_button = QPushButton('打断')
        self.interrupt_button.setEnabled(False)
        self.interrupt_button.clicked.connect(lambda: self.voice.interrupt() if self.voice_active and self.voice else None)
        controls.addWidget(self.interrupt_button)
        self.read_aloud = QCheckBox('朗读回复')
        controls.addWidget(self.read_aloud)
        controls.addStretch()
        self.stop_button = QPushButton('停止')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_turn)
        controls.addWidget(self.stop_button)
        self.send_button = QPushButton('发送 ↑')
        self.send_button.setObjectName('Primary')
        self.send_button.clicked.connect(self.send)
        controls.addWidget(self.send_button)
        layout.addLayout(controls)
        hint = QLabel('Enter 发送 · Shift+Enter 换行 · 阿里负责实时通话，DeepSeek 回答问题并执行任务')
        hint.setObjectName('Muted')
        layout.addWidget(hint)
        splitter.addWidget(body)
        splitter.setSizes([240, 720])
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.refresh_tree()
        saved = self.store.preference('active_conversation')
        ids = [c['id'] for c in self.store.snapshot()['conversations']]
        self.open_conversation(saved if saved in ids else (ids[0] if ids else self.store.create_conversation()))

    def _pin(self, enabled):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.show()

    def hide_to_pet(self):
        self.hide()
        self.pet._show_agent_bubble('我在听，可以继续说。' if self.voice_active else '点击这里，继续我们的对话。',self.active_id)

    def refresh_tree(self):
        self.tree.clear()
        snapshot = self.store.snapshot(self.show_archived)
        groups = {}
        root = QTreeWidgetItem(self.tree, ['独立对话' if not self.show_archived else '已归档'])
        groups[None] = root
        for p in snapshot['projects']:
            item = QTreeWidgetItem(self.tree, [p['name']])
            item.setData(0, Qt.UserRole, ('project', p['id']))
            groups[p['id']] = item
        for c in snapshot['conversations']:
            item = QTreeWidgetItem(groups.get(c['project_id'], root), ['◌  ' + c['name']])
            item.setToolTip(0, c['name'])
            item.setData(0, Qt.UserRole, ('conversation', c['id']))
            if c['id'] == self.active_id:
                self.tree.setCurrentItem(item)
        self.tree.expandAll()
        if self.active_id:
            self.title.setText(self.store.conversation(self.active_id)['name'])

    def _selected(self, item, column=0):
        data = item.data(0, Qt.UserRole)
        if data and data[0] == 'conversation':
            if self.busy or self.voice_active:
                self.status.setText('请先结束本轮或语音通话，再切换会话')
                return
            self.open_conversation(data[1])

    def open_conversation(self, ident):
        self.active_id = ident
        self.store.preference('active_conversation', ident)
        self.refresh_tree()
        self.render()

    def render(self):
        messages = self.store.messages(self.active_id)
        if not messages:
            self.view.setHtml('''<div style="margin-top:80px;text-align:center;color:#303a50">
                <p style="font-size:42px">🐧</p><h2>咕嘎在这里。</h2>
                <p style="color:#949baa">聊个想法，或者交给本鹅一件小事。</p>
                <p style="color:#b1b6c0;font-size:12px">“把自己移到左边”　“新建一个学习项目”<br><br>
                “先自己想一想，再帮我整理思路”</p></div>''')
            return
        parts = []
        for m in messages:
            role = m['role']
            color = '#edf1ff' if role == 'user' else ('#f5f6f8' if role in ('tool', 'system') else '#ffffff')
            who = {'user': '你', 'assistant': '咕嘎', 'tool': '操作记录', 'system': '提示'}[role]
            text = html.escape(m['content']).replace('\n', '<br>')
            if role == 'tool':
                key = str(m['id'])
                summary = m['content'].split('\n', 1)[0]
                if key not in self.expanded_logs:
                    text = html.escape(summary) + f' &nbsp; <a href="guga-log:{key}" style="color:#6d7ec0">查看详情</a>'
                else:
                    text += f'<br><a href="guga-log:{key}">收起详情</a>'
            parts.append(f'<table width="100%" cellspacing="0" cellpadding="13" style="margin-top:10px;background:{color}">'
                         f'<tr><td><span style="font-size:11px;color:#8992a3">{who}</span><br>'
                         f'<p style="line-height:1.6">{text}</p></td></tr></table>')
        self.view.setHtml(''.join(parts))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def _log_link(self, url):
        if url.scheme() == 'guga-log':
            key = url.path()
            if key in self.expanded_logs:
                self.expanded_logs.remove(key)
            else:
                self.expanded_logs.add(key)
            self.render()

    def open_permissions(self):
        from ui.app_permissions import AppPermissionsDialog
        AppPermissionsDialog(self.runtime.apps, self).exec_()

    def _project_selection(self):
        item = self.tree.currentItem()
        data = item.data(0, Qt.UserRole) if item else None
        if data:
            return data[1] if data[0] == 'project' else self.store.conversation(data[1])['project_id']
        return None

    def new_conversation(self):
        if self.busy or self.voice_active:
            return
        self.show_archived = False
        self.open_conversation(self.store.create_conversation(project_id=self._project_selection()))

    def new_project(self):
        name, ok = QInputDialog.getText(self, '新建项目', '项目名称')
        if ok and name.strip():
            self._guard(lambda: self.store.create_project(name))

    def _guard(self, callback):
        try:
            callback()
            self.refresh_tree()
        except Exception as exc:
            self.status.setText(str(exc))

    def _rename_item(self, item, column=0):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        old_name = (self.store.conversation(data[1])['name'] if data[0] == 'conversation' else
                    next(p['name'] for p in self.store.snapshot()['projects'] if p['id'] == data[1]))
        name, ok = QInputDialog.getText(self, '更名', '新名称', text=old_name)
        if ok and name.strip():
            self._guard(lambda: self.store.rename(data[0], data[1], name))

    def rename_active(self):
        name, ok = QInputDialog.getText(self, '更名对话', '对话名称', text=self.store.conversation(self.active_id)['name'])
        if ok and name.strip():
            self._guard(lambda: self.store.rename('conversation', self.active_id, name))

    def _context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item or not item.data(0, Qt.UserRole):
            return
        kind, ident = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        menu.addAction('更名').triggered.connect(lambda: self._rename_item(item))
        if kind == 'conversation':
            move = menu.addMenu('移动到项目')
            move.addAction('独立对话').triggered.connect(lambda: self._guard(lambda: self.store.move(ident, None)))
            for p in self.store.snapshot()['projects']:
                move.addAction(p['name']).triggered.connect(lambda checked=False, pid=p['id']: self._guard(lambda: self.store.move(ident, pid)))
            menu.addAction('恢复' if self.show_archived else '归档').triggered.connect(
                lambda: self._guard(lambda: self.store.archive(ident, not self.show_archived)))
        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def _toggle_archive(self):
        self.show_archived = not self.show_archived
        self.archive_button.setText('返回全部对话' if self.show_archived else '已归档对话')
        self.refresh_tree()

    def eventFilter(self, obj, event):
        if obj is self.editor and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Enter, Qt.Key_Return) and not event.modifiers() & Qt.ShiftModifier:
                self.send()
                return True
        return super().eventFilter(obj, event)

    def send(self, text=None, record_user=True):
        text = text if isinstance(text, str) else self.editor.toPlainText().strip()
        if not text.strip():
            return
        if self.busy:
            if any(word in text for word in ('停止任务','取消任务','停止执行','别执行了')):
                self.agent.cancel();self.status.setText('已请求停止任务');self.editor.clear();return True
            self.agent.steer(text)
            if record_user:self.store.append(self.active_id,'user',text)
            self.editor.clear();self.status.setText('追加要求已排队；当前操作结束后处理');self.render()
            return True
        if len(text) > 16000:
            self.status.setText('单条消息最多 16000 字，请分段发送')
            return
        history = self.store.messages(self.active_id, 40)
        try:
            self.agent.start(self.active_id, history, text)
        except Exception as exc:
            self.status.setText(str(exc))
            return False
        self.busy = True
        self.pet._tts.stop()
        if record_user:
            self.store.append(self.active_id, 'user', text)
        if self.store.conversation(self.active_id)['name'] == '新对话':
            self.store.rename('conversation', self.active_id, text.replace('\n', ' ')[:24])
        self.editor.clear()
        self.send_button.setEnabled(True)
        self.new_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText('咕嘎正在思考…')
        self._task_started=time.monotonic()
        self._last_task_notice=self._task_started
        self._task_summary='正在规划第一步，尚未修改目标文件'
        self._task_heartbeat_timer.start()
        self.refresh_tree()
        self.render()
        return True

    def _activity(self, ident, event):
        result = event['result']
        label = {'app_state': '查看自身状态', 'pet_control': '操纵自身', 'workspace': '管理项目与会话',
                 'self_ask': '自己询问自己', 'ecosystem': '调用生态软件', 'applications': '授权软件操作'}.get(event['name'], event['name'])
        label += ' · ' + ('完成' if result.get('ok') else '未完成')
        text = label + '\n' + json.dumps(event['arguments'], ensure_ascii=False)
        text += '\n' + ('完成：' if result.get('ok') else '失败：') + json.dumps(result, ensure_ascii=False)[:6000]
        self.store.append(ident, 'tool', text)
        if ident == self.active_id:
            self.status.setText(label + (' · 已完成' if result.get('ok') else ' · 未完成'))
            self.render()

    def _task_progress(self,ident,event):
        if ident!=self.active_id:return
        summary=event.get('summary','正在执行任务')
        self._task_summary=summary
        self.status.setText(summary[:120])
        if self.busy and time.monotonic()-self._task_started>3 and not self.isVisible():
            if not (self.voice_active and self.voice and self.voice.is_speaking):self.pet._show_agent_bubble(summary,ident)

    def _task_heartbeat(self):
        if not self.busy:
            self._task_heartbeat_timer.stop();return
        if time.monotonic()-self._last_task_notice<12:return
        self._last_task_notice=time.monotonic()
        self._task_feedback_sequence+=1
        elapsed=int(time.monotonic()-self._task_started) if self._task_started else 0
        summary=f'已运行 {elapsed} 秒，还在处理：'+self._task_summary[:90]+'。你可以补充要求，或说停止任务。'
        self.pet._show_agent_bubble(summary,self.active_id)
        if self.voice_active and self.voice:
            self.voice.notify_battleground('task-update-'+str(self._task_feedback_sequence),summary)

    def _battleground_event(self, event):
        ident = event.get('conversation_id')
        if not ident:
            return
        speech = event.get('speech')
        if speech:
            self.store.append(ident, 'system', speech)
            if self.active_id == ident:
                self.status.setText(speech[:100])
                self.render()
                if self.voice_active and self.voice:
                    self.voice.notify_battleground(event['event_id'], speech)
        elif event['type'] in ('action_confirmed','unconfirmed','input_sent','memory_snapshot'):
            self.store.append(ident, 'tool', '战棋后台 · '+json.dumps(event,ensure_ascii=False)[:6000])
            if self.active_id == ident:
                self.render()

    def _completed(self, result):
        self.busy = False
        self._task_heartbeat_timer.stop()
        self.send_button.setEnabled(True)
        self.new_button.setEnabled(not self.voice_active)
        self.stop_button.setEnabled(False)
        ident = result['conversation_id']
        if self.agent.cancel_event.is_set():
            result = dict(result, ok=False, error='本轮已停止，已完成的操作保留在记录中')
        voice_task = self._voice_task
        self._voice_task = None
        if voice_task and self.voice_active and voice_task[0] is self.voice:
            self._voice_readback = True
            self.voice.resolve_task(voice_task[1], dict(ok=result['ok'],
                answer=result.get('text', '') if result['ok'] else '', error=result.get('error', '')))
        elif self.voice_active and self.voice:
            self._voice_readback=True
            self.voice.notify_battleground('task-finished-'+result.get('task_id',ident),
                '任务执行结果：'+(result.get('text','') if result['ok'] else result.get('error','未完成')))
        if result['ok']:
            self.store.append(ident, 'assistant', result['text'])
            if not self.voice_active and not self.isVisible():
                self.pet._show_agent_bubble(result['text'],ident)
            self.status.setText('●  就绪')
            if self.read_aloud.isChecked() and not self.voice_active:
                self.pet._say_with_expression(result['text'], result['expression'], result['action'])
            else:
                self.pet._anim.set_expression(result['expression'])
                if result['action'] != 'none':
                    if self.voice_active:self.pet._queue_voice_gesture(result['action'])
                    else:self.pet._perform_gesture(result['action'])
        else:
            self.store.append(ident, 'system', result.get('error', '本轮未完成'))
            self.status.setText(result.get('error', '本轮未完成'))
        if self.active_id == ident:
            self.render()

    def stop_turn(self):
        self.runtime.battleground.stop()
        self.agent.cancel()
        self.pet._tts.stop()
        if self.voice_active:
            self.voice_button.setChecked(False)
        self.status.setText('已请求停止 · 不再执行后续操作')

    def toggle_voice(self, enabled):
        if enabled:
            if self.pet._realtime_active() or getattr(self.pet, '_recording', False):
                self.status.setText('请先结束原语音通话，再开启智能体语音')
                self.voice_button.setChecked(False)
                return
            if self.voice and self.voice.active:
                self.status.setText('上一段语音正在释放麦克风，请稍后重试')
                self.voice_button.setChecked(False)
                return
            self.pet._voice_mode = False
            from core.realtime_voice import load_settings, connection_url
            from ui.voice_dialog import VoiceSettingsDialog
            cfg = load_settings()
            try:
                connection_url(cfg)
            except ValueError:
                if VoiceSettingsDialog(self).exec_() != QDialog.Accepted:
                    self.voice_button.setChecked(False)
                    return
                cfg = load_settings()
            self.voice_active = True
            self._voice_readback = False
            if self.voice:
                self.voice.deleteLater()
            self.voice = AgentRealtimeVoice(self)
            self.voice.context_history = [('饲养员' if m['role'] == 'user' else '咕嘎', m['content'])
                for m in self.store.messages(self.active_id, 40) if m['role'] in ('user', 'assistant')]
            self.voice.task_requested.connect(self._voice_request)
            self.voice.tasks_cancelled.connect(self._voice_cancelled)
            self.voice.transcript.connect(self._voice_transcript)
            self.voice.preview.connect(self._voice_preview)
            self.voice.gesture.connect(self.pet._queue_voice_gesture)
            self.voice.status.connect(self.status.setText)
            self.voice.failed.connect(self._voice_error)
            self.voice.finished.connect(self._voice_finished)
            self.voice.speaking.connect(self.pet._on_realtime_speaking)
            if self.pet._voice_call_panel:
                self.pet._voice_call_panel.close()
                self.pet._voice_call_panel.deleteLater()
                self.pet._voice_call_panel = None
            self.pet._realtime_voice = self.voice
            self.pet._tts.stop()
            self.new_button.setEnabled(False)
            self.voice_settings_button.setEnabled(False)
            self.mute_button.setEnabled(True)
            self.interrupt_button.setEnabled(True)
            self.read_aloud.setEnabled(False)
            self.voice_button.setText('■  结束语音')
            self.pet._agent_bubble.set_call_active(True,self.active_id)
            self.voice.start(cfg)
        else:
            self.voice_active = False
            self.pet._pending_voice_gesture=None
            self.agent.cancel()
            self.runtime.battleground.stop()
            if self.voice:
                self.voice.stop()
            self._voice_cancelled()
            self.new_button.setEnabled(not self.busy)
            self.voice_settings_button.setEnabled(True)
            self.mute_button.setEnabled(False)
            self.mute_button.setChecked(False)
            self.interrupt_button.setEnabled(False)
            self.read_aloud.setEnabled(True)
            self.voice_button.setText('语音对话')
            self.pet._agent_bubble.set_call_active(False,self.active_id)

    def _voice_error(self, message):
        self.voice_button.setChecked(False)
        self.status.setText(message)
        self.pet._show_agent_bubble(message,self.active_id)

    def open_voice_settings(self):
        from ui.voice_dialog import VoiceSettingsDialog
        VoiceSettingsDialog(self).exec_()

    def _voice_request(self, call_id, request):
        if not self.voice_active or self.sender() is not self.voice:
            return
        if self.busy:
            if any(word in request for word in ('停止任务','取消任务','停止执行','别执行了')):
                self.agent.cancel()
                self.voice.resolve_task(call_id,dict(ok=True,answer='已请求停止任务；已完成的操作保留在记录中。'))
            elif any(word in request for word in ('进度','进展','做到哪','怎么样了','在做什么')):
                state=self.agent.task_status()
                self.voice.resolve_task(call_id,dict(ok=True,answer=state.get('summary','任务正在执行')+'；已完成工具操作'+str(len(state.get('events',[])))+'次。'))
            else:
                self.agent.steer(request)
                self.voice.resolve_task(call_id,dict(ok=True,answer='收到追加要求，当前操作结束后会一起处理。'))
            return
        self._voice_task = (self.voice, call_id)
        messages = self.store.messages(self.active_id, 1)
        record_user = not (messages and messages[-1]['role'] == 'user')
        if not self.send(request, record_user=record_user):
            self._voice_task = None
            self.voice.resolve_task(call_id, dict(ok=False, error=self.status.text()))
        else:
            from core.task_feedback import acknowledgement
            ack=acknowledgement(request)
            # Close the speech FC immediately; execution remains in the worker.
            # Otherwise pending _tasks blocks every queued progress narration.
            self._voice_task=None
            self._voice_readback=True
            self.voice.resolve_task(call_id,dict(ok=True,answer=ack,execution_pending=True))
            self.pet._show_agent_bubble(ack,self.active_id)
            self.store.append(self.active_id,'system','任务已接收：'+ack)

    def _voice_cancelled(self):
        if self._voice_task:
            self._voice_task = None
            # Speech interruption stops old playback, not a still-authorized task.
            # Explicit stop/end-call/shutdown still cancels the worker.
            if not self.voice_active:self.agent.cancel()

    def _voice_preview(self, text):
        if self.voice_active and self.sender() is self.voice:
            from core.embodiment import spoken_reply
            self.pet._show_agent_bubble(spoken_reply(text)[2],self.active_id)

    def _voice_transcript(self, who, text):
        if not self.voice_active or self.sender() is not self.voice:
            return
        if who!='饲养员':
            from core.embodiment import spoken_reply
            _,_,text=spoken_reply(text)
        if who == '饲养员':
            self._voice_readback = False
            self.store.append(self.active_id, 'user', text)
            if self.store.conversation(self.active_id)['name'] == '新对话':
                self.store.rename('conversation', self.active_id, text[:24])
                self.refresh_tree()
        elif not self._voice_readback:
            self.store.append(self.active_id, 'assistant', text)
        if who != '饲养员':
            self.pet._show_agent_bubble(text,self.active_id)
        self.render()

    def _voice_finished(self):
        if self.sender() is self.voice:
            self.voice_button.setChecked(False)
            if not self.voice.last_error:
                self.status.setText('通话已结束 · 阿里语音连接已关闭')

    def shutdown(self):
        self._task_heartbeat_timer.stop()
        self.runtime.battleground.stop()
        self.agent.cancel()
        self.voice_button.setChecked(False)

    def closeEvent(self, event):
        self.shutdown()
        self.pet._tts.stop()
        event.accept()

    def reject(self):
        self.close()
