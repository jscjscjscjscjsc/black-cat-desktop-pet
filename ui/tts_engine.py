# -*- coding: utf-8 -*-
"""TTS 语音合成引擎 — 黑猫版（支持 豆包语音V3新版API Key + edge-tts）"""
import os, sys, asyncio, threading, tempfile, time, uuid, json, base64
from PyQt5.QtCore import QObject, pyqtSignal, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent


class TTSEngine(QObject):
    """语音合成引擎

    优先级: 豆包语音V3 > edge-tts > 静默
    - 豆包语音V3: 使用新版API Key方式接入（seed-tts-2.0模型）
    - edge-tts: 免费，微软神经语音

    黑猫音色：zh_female_mizai_saturn_bigtts（黑猫侦探社咪仔，慵懒傲娇风格）
    """

    speak_finished = pyqtSignal()
    speak_started = pyqtSignal(str)

    EDGE_VOICE = "zh-CN-XiaoyiNeural"
    EDGE_RATE = "-8%"
    EDGE_PITCH = "-8Hz"

    DOUBAO_API_KEY = "9ec1142f-96a4-45a5-93b0-6b2031d18589"
    DOUBAO_VOICE = "zh_female_mizai_saturn_bigtts"
    DOUBAO_SPEED = -15
    DOUBAO_RESOURCE = "seed-tts-2.0"

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer()
        self._player.setVolume(80)
        self._player.stateChanged.connect(self._on_state_changed)
        self._temp_files = []
        self._is_speaking = False
        self._session = None

        self._use_doubao = bool(self.DOUBAO_API_KEY)
        self._use_edge = self._check_edge_tts()

        if self._use_doubao:
            try:
                import requests
                self._session = requests.Session()
            except ImportError:
                self._use_doubao = False

        print(f"[TTS] 豆包语音V3: {'可用' if self._use_doubao else '未配置'}")
        print(f"[TTS] edge-tts: {'可用' if self._use_edge else '不可用'}")

    def _check_edge_tts(self):
        try:
            import edge_tts
            return True
        except ImportError:
            return False

    def speak(self, text: str):
        if not text.strip():
            return
        self.stop()
        self._is_speaking = True
        self.speak_started.emit(text)
        thread = threading.Thread(target=self._synth_and_play, args=(text,), daemon=True)
        thread.start()

    def stop(self):
        if self._is_speaking:
            self._player.stop()
            self._is_speaking = False

    def _synth_and_play(self, text: str):
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False,
                                             dir=tempfile.gettempdir())
            tmp_path = tmp.name
            tmp.close()
            self._temp_files.append(tmp_path)

            success = False
            if self._use_doubao:
                success = self._synth_doubao(text, tmp_path)

            if not success and self._use_edge:
                success = self._synth_edge(text, tmp_path)

            if not success:
                print(f"[TTS] 语音合成失败，跳过播放")
                self._is_speaking = False
                return

            url = QUrl.fromLocalFile(tmp_path)
            content = QMediaContent(url)
            self._player.setMedia(content)
            self._player.play()
            print(f"[TTS] 正在播放: {text[:30]}...")

        except Exception as e:
            print(f"[TTS] 错误: {e}")
            self._is_speaking = False

    def _synth_edge(self, text: str, out_path: str) -> bool:
        try:
            import edge_tts

            async def _synth():
                communicate = edge_tts.Communicate(
                    text, self.EDGE_VOICE,
                    rate=self.EDGE_RATE,
                    pitch=self.EDGE_PITCH,
                    volume="+0%"
                )
                await communicate.save(out_path)

            asyncio.run(_synth())
            return os.path.exists(out_path) and os.path.getsize(out_path) > 100

        except Exception as e:
            print(f"[TTS] edge-tts 错误: {e}")
            return False

    def _synth_doubao(self, text: str, out_path: str) -> bool:
        try:
            import requests
            sess = self._session or requests
            url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
            headers = {
                "Content-Type": "application/json",
                "X-Api-Key": self.DOUBAO_API_KEY,
                "X-Api-Resource-Id": self.DOUBAO_RESOURCE,
                "X-Api-Request-Id": str(uuid.uuid4()),
            }
            body = {
                "user": {"uid": "black_cat_pet"},
                "req_params": {
                    "text": text,
                    "speaker": self.DOUBAO_VOICE,
                    "audio_params": {
                        "format": "mp3",
                        "sample_rate": 24000,
                        "speech_rate": self.DOUBAO_SPEED,
                    }
                }
            }

            resp = sess.post(url, headers=headers, json=body, timeout=30, stream=True)
            audio_parts = []
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    j = json.loads(line.decode('utf-8'))
                    code = j.get("code", -1)
                    if code == 0:
                        d = j.get("data")
                        if d:
                            audio_parts.append(base64.b64decode(d))
                    elif code == 20000000:
                        break
                    elif code not in (0, 20000000):
                        msg = j.get("message", "")
                        print(f"[TTS] 豆包语音响应错误 code={code}: {msg[:100]}")
                except Exception:
                    continue

            if audio_parts:
                audio_data = b"".join(audio_parts)
                with open(out_path, 'wb') as f:
                    f.write(audio_data)
                return True
            return False

        except Exception as e:
            print(f"[TTS] 豆包语音错误: {e}")
            return False

    def _on_state_changed(self, state):
        if state == QMediaPlayer.StoppedState and self._is_speaking:
            self._is_speaking = False
            self.speak_finished.emit()
            self._cleanup_temp()

    def _cleanup_temp(self):
        for f in self._temp_files[:]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass
        self._temp_files.clear()

    @property
    def is_speaking(self):
        return self._is_speaking
