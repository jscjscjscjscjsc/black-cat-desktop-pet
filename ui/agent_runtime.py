"""Application-owned tool registry; the same handlers serve typed and spoken commands."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


class AppRuntime:
    def __init__(self, pet, panel, store):
        self.pet, self.panel, self.store = pet, panel, store
        from core.authorized_apps import AuthorizedApps
        self.apps = AuthorizedApps()

    def execute(self, name, args):
        if name == 'applications':
            if args.get('action') == 'list':
                return {'authorized_apps': list(self.apps.entries())}
            if args.get('action') == 'open':
                return self.apps.open(args['name'])
            raise ValueError('未知软件操作')
        if name == 'confirm_external':
            from PyQt5.QtWidgets import QMessageBox
            from PyQt5.QtCore import QTimer
            import json
            box = QMessageBox(self.panel)
            box.setWindowTitle('咕嘎 · 确认软件操作')
            box.setText('此工具尚未被标记为可直接执行的常规操作，是否允许本次调用？')
            box.setInformativeText(args['server'] + ' / ' + args['tool'] + '\n' + json.dumps(args.get('arguments', {}), ensure_ascii=False)[:1500])
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            QTimer.singleShot(30000, box.reject)
            cancel_timer = QTimer(box)
            cancel_timer.setInterval(100)
            cancel_timer.timeout.connect(lambda: box.reject() if self.panel.agent.cancel_event.is_set() else None)
            cancel_timer.start()
            approved = box.exec_() == QMessageBox.Yes
            cancel_timer.stop()
            return {'approved': approved}
        if name == 'app_state':
            return dict(pet=dict(x=self.pet.x(), y=self.pet.y(), visible=self.pet.isVisible(),
                                opacity=self.pet.windowOpacity(), status=self.pet._status.snapshot(),
                                volume=self.pet._tts._player.volume()),
                        current_conversation_id=self.panel.active_id,
                        voice_active=self.panel.voice_active,
                        workspace=self.store.snapshot(),
                        authorized_apps=list(self.apps.entries()),
                        capabilities=['pet_control', 'workspace', 'applications', 'self_ask', 'ecosystem'],
                        scope='咕嘎应用自身；不包含任意系统命令或修改源码')
        if name == 'pet_control':
            return self._pet(args)
        if name == 'workspace':
            return self._workspace(args)
        raise ValueError('该工具未注册')

    def _pet(self, args):
        pet = self.pet
        action = args.get('action')
        if action == 'move':
            x, y = int(args['x']), int(args['y'])
            screens = QApplication.screens()
            screen = next((s for s in screens if s.availableGeometry().contains(x, y)), QApplication.primaryScreen())
            g = screen.availableGeometry()
            x = max(g.left(), min(x, g.right() - pet.width() + 1))
            y = max(g.top(), min(y, g.bottom() - pet.height() + 1))
            pet.move(x, y)
            pet._save_state()
            return dict(x=pet.x(), y=pet.y())
        if action == 'show':
            pet.show()
            pet._force_top()
        elif action == 'hide':
            pet.hide()
        elif action == 'reset_position':
            pet._reset_pos()
        elif action == 'animate':
            name = args.get('name', 'bounce')
            if name not in ('bounce', 'shake', 'point', 'peek', 'tsundere'):
                raise ValueError('未知动画')
            pet._say_with_expression('', 'happy', name)
        elif action == 'interact':
            name = args.get('name', '')
            if name not in ('feed', 'play', 'pet', 'sleep', 'dance'):
                raise ValueError('未知互动')
            pet._act(name)
        elif action == 'set_opacity':
            value = float(args['value'])
            if not .3 <= value <= 1:
                raise ValueError('透明度需要在 0.3—1 之间')
            pet.setWindowOpacity(value)
            pet._config.opacity = value
        elif action == 'set_volume':
            value = int(args['value'])
            if not 0 <= value <= 100:
                raise ValueError('音量需要在 0—100 之间')
            pet._tts._player.setVolume(value)
            pet._config._s.setValue('agent/volume', value)
        elif action == 'set_topmost':
            enabled = bool(args['value'])
            pet.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
            pet.show()
            pet._config._s.setValue('agent/topmost', enabled)
        elif action == 'set_bongo':
            if args['value']:
                pet._show_bongo()
            else:
                pet._bongo.hide()
                pet._bongo_on = False
                pet.setFixedSize(pet._iw, pet._ih)
        elif action == 'open_chat':
            self.panel.show()
            self.panel.raise_()
        elif action == 'open_voice_settings':
            # Deferred to avoid blocking the queued tool callback in a modal dialog.
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, pet._configure_realtime_voice)
            return {'opened': '语音设置', 'state': '已请求打开，等待用户设置'}
        elif action == 'open_battleground_lab':
            pet._open_bg_agent()
        elif action == 'open_battleground_live':
            pet._open_bg_live()
        else:
            raise ValueError('未注册的自身操作')
        return dict(action=action, visible=pet.isVisible(), x=pet.x(), y=pet.y())

    def _workspace(self, args):
        action = args.get('action')
        ident = args.get('id') or self.panel.active_id
        result = {}
        if action == 'create_project':
            result['project_id'] = self.store.create_project(args['name'])
        elif action == 'rename_project':
            if not args.get('id'):
                raise ValueError('更名项目需要明确的项目 ID')
            self.store.rename('project', ident, args['name'])
        elif action == 'new_conversation':
            result['conversation_id'] = self.store.create_conversation(args.get('name', '新对话'), args.get('project_id') or None)
            # Keep this running turn bound to its original conversation.
        elif action == 'rename_conversation':
            self.store.rename('conversation', ident, args['name'])
        elif action == 'move_conversation':
            self.store.move(ident, args.get('project_id') or None)
        elif action == 'archive_conversation':
            self.store.archive(ident)
        elif action == 'restore_conversation':
            self.store.archive(ident, False)
        elif action == 'list_archived':
            return self.store.snapshot(archived=True)
        else:
            raise ValueError('未注册的会话操作')
        self.panel.refresh_tree()
        return dict(result, workspace=self.store.snapshot())
