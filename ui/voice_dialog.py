"""Local-only credential setup and explicit realtime call controls."""
import json
import os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QPushButton, QLabel,
    QDialogButtonBox, QMessageBox, QPlainTextEdit)
from core.realtime_voice import CONFIG_PATH, DEFAULTS, connection_url


class VoiceSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('咕嘎 · 阿里实时语音配置')
        self.setMinimumWidth(560)
        try:
            with CONFIG_PATH.open(encoding='utf-8-sig') as f:
                self._config = json.load(f)
        except FileNotFoundError:
            self._config = {}
        cfg = dict(DEFAULTS, **self._config.get('realtime_voice', {}))
        layout = QVBoxLayout(self)
        note = QLabel('选择阿里云百炼 → 北京地域 → 业务空间。\nKey只保存到本机 ai_config.json，已由Git忽略。')
        note.setWordWrap(True)
        layout.addWidget(note)
        link = QLabel('<a href="https://bailian.console.aliyun.com/">打开百炼控制台登录</a> · '
                      '<a href="https://help.aliyun.com/zh/model-studio/realtime">官方模型说明</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        form = QFormLayout()
        layout.addLayout(form)
        self.key = QLineEdit(cfg.get('api_key', ''))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('百炼 API Key；也可用 DASHSCOPE_API_KEY 环境变量')
        form.addRow('API Key', self.key)
        self.workspace = QLineEdit(cfg.get('workspace_id', ''))
        self.workspace.setPlaceholderText('该Key所属的业务空间ID')
        form.addRow('业务空间 ID', self.workspace)
        self.region = QComboBox()
        self.region.addItem('北京（中国内地）', 'cn-beijing')
        self.region.addItem('新加坡', 'ap-southeast-1')
        self.region.setCurrentIndex(max(0, self.region.findData(cfg.get('region'))))
        form.addRow('地域', self.region)
        self.model = QComboBox()
        self.model.addItems(['qwen-audio-3.1-realtime-plus', 'qwen3.8-omni-flash-realtime', 'qwen3.5-omni-plus-realtime',
                             'qwen3.5-omni-flash-realtime'])
        self.model.setCurrentText(cfg['model'])
        form.addRow('实时语音模型', self.model)
        self.voice = QComboBox()
        self.voice.setEditable(True)
        self.voice.addItems(['longanqian_v3.1', 'Tina', 'Cici', 'Momo', 'Serena', 'Ethan'])
        self.voice.setCurrentText(cfg['voice'])
        form.addRow('音色', self.voice)
        self.free_guard = QCheckBox('已在百炼为当前模型开启“免费额度用完即停”')
        self.free_guard.setChecked(cfg.get('free_quota_confirmed_model') == cfg['model'])
        form.addRow('只用赠送额度', self.free_guard)
        self.model.currentTextChanged.connect(lambda _: self.free_guard.setChecked(False))
        self.model.currentTextChanged.connect(lambda model: self.voice.setCurrentText(
            'longanqian_v3.1' if model.startswith('qwen-audio-') else 'Tina'))
        quota_note = QLabel('未勾选也可保存配置，但程序会阻止联网。必须先开启阿里服务端开关。\n免费额度耗尽或到期后停止，不自动换模型。')
        quota_note.setWordWrap(True)
        layout.addWidget(quota_note)
        self.headphones = QCheckBox('使用耳机：允许边听边说和语音打断')
        self.headphones.setChecked(cfg['headphones'])
        form.addRow('收音模式', self.headphones)
        tip = QLabel('外放时，咕嘎说话期间暂停收音以避免回声；可用“打断”按钮。\n耳机模式没有软件回声消除，建议佩戴耳机。')
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.input_device = QComboBox()
        self.output_device = QComboBox()
        for combo in (self.input_device, self.output_device):
            combo.addItem('系统默认设备', None)
        try:
            import sounddevice as sd
            for i, dev in enumerate(sd.query_devices()):
                if dev['max_input_channels']:
                    self.input_device.addItem(f"{i}: {dev['name']}", i)
                if dev['max_output_channels']:
                    self.output_device.addItem(f"{i}: {dev['name']}", i)
        except Exception:
            pass
        for key, combo in [('input_device', self.input_device), ('output_device', self.output_device)]:
            combo.setCurrentIndex(max(0, combo.findData(cfg.get(key))))
            form.addRow('麦克风' if key == 'input_device' else '扬声器', combo)
        self.silence = QSpinBox()
        self.silence.setRange(200, 6000)
        self.silence.setSuffix(' 毫秒')
        self.silence.setValue(cfg['silence_duration_ms'])
        form.addRow('停顿等待（长表达可调大）', self.silence)
        self.duration = QSpinBox()
        self.duration.setRange(10, 480)
        self.duration.setValue(cfg['max_call_minutes'])
        self.duration.setSuffix(' 分钟')
        form.addRow('本次通话时限', self.duration)
        self.idle = QSpinBox()
        self.idle.setRange(1, 60)
        self.idle.setValue(cfg['idle_minutes'])
        self.idle.setSuffix(' 分钟')
        form.addRow('无交谈自动结束', self.idle)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        cfg = dict(DEFAULTS, api_key=self.key.text().strip(), workspace_id=self.workspace.text().strip(),
                   region=self.region.currentData(), model=self.model.currentText(),
                   voice=self.voice.currentText().strip(), headphones=self.headphones.isChecked(),
                   silence_duration_ms=self.silence.value(), max_call_minutes=self.duration.value(),
                   idle_minutes=self.idle.value(), input_device=self.input_device.currentData(),
                   output_device=self.output_device.currentData(), free_only=True,
                   free_quota_confirmed_model=self.model.currentText() if self.free_guard.isChecked() else '')
        try:
            checked = dict(cfg)
            checked['api_key'] = checked['api_key'] or os.getenv('DASHSCOPE_API_KEY', '')
            checked['workspace_id'] = checked['workspace_id'] or os.getenv('DASHSCOPE_WORKSPACE_ID', '')
            connection_url(checked)
            # Re-read immediately before save to preserve unrelated current configuration.
            try:
                with CONFIG_PATH.open(encoding='utf-8-sig') as f:
                    current = json.load(f)
            except FileNotFoundError:
                current = {}
            current['realtime_voice'] = cfg
            tmp = CONFIG_PATH.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, CONFIG_PATH)
        except Exception as exc:
            QMessageBox.warning(self, '配置未保存', str(exc))
            return
        self.accept()


class VoiceCallDialog(QDialog):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle('咕嘎 · 持续语音通话')
        self.resize(580, 430)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)
        self.status = QLabel('准备连接…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.document().setMaximumBlockCount(300)
        layout.addWidget(self.transcript)
        note = QLabel('通话开启时麦克风音频会发往阿里百炼，并按其API计费。\n关闭窗口即结束通话；不保存录音或对话到磁盘。')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.mute = QPushButton('静音麦克风')
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self._mute)
        row.addWidget(self.mute)
        interrupt = QPushButton('打断咕嘎')
        interrupt.clicked.connect(engine.interrupt)
        row.addWidget(interrupt)
        end = QPushButton('结束通话')
        end.clicked.connect(self.close)
        row.addWidget(end)
        layout.addLayout(row)
        engine.status.connect(self.status.setText)
        engine.transcript.connect(self._append)
        engine.failed.connect(self._error)
        engine.finished.connect(self._finished)

    def _mute(self, on):
        self.engine.mute(on)
        self.mute.setText('开启麦克风' if on else '静音麦克风')

    def _append(self, who, text):
        self.transcript.appendPlainText(f'{who}：{text}\n')

    def _error(self, message):
        self.status.setText(message)
        self.transcript.appendPlainText('连接提示：' + message)

    def _finished(self):
        self.mute.setEnabled(False)
        if not self.engine.last_error:
            self.status.setText('通话已结束 · 麦克风已释放')
        self.transcript.appendPlainText('通话已结束。需要继续时，从桌宠菜单重新开始。')

    def closeEvent(self, event):
        self.engine.stop()
        event.accept()
