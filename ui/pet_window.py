# -*- coding: utf-8 -*-
"""黑猫桌宠主窗口 — 透明悬浮（基于猫咪精灵图的多层局部变形动画）"""
import ctypes, os, sys, logging, random, math

logging.basicConfig(
    filename=os.path.join(os.path.dirname(__file__), '..', 'pet_debug.log'),
    level=logging.WARNING, format='%(asctime)s %(message)s'
)

from PyQt5.QtCore import Qt, QPoint, QTimer, QRect, QElapsedTimer
from PyQt5.QtGui import (
    QPixmap, QBitmap, QIcon, QPainter, QColor, QFont,
    QFontMetrics, QPen, QPainterPath, QImage
)
from PyQt5.QtWidgets import (
    QWidget, QMenu, QSystemTrayIcon, QApplication
)

from ui.bongo_panel import BongoPanel
from ui.sprite_animator import SpriteAnimator
from ui.tts_engine import TTSEngine
from ui.speech_system import get_speech, SPEECHES
from core.keyboard_hook import KeyboardHook
from core.status_system import StatusSystem
from core.interaction import get_action, ACTIONS
from core.config_manager import ConfigManager

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOSIZE = 1; SWP_NOMOVE = 2; SWP_NOACTIVATE = 16; SWP_SHOWWINDOW = 64
HWND_TOPMOST = -1; HWND_NOTOPMOST = -2


class PetWindow(QWidget):
    RES_DIR = os.path.join(os.path.dirname(__file__), '..', 'resources')

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._config = ConfigManager()

        # 窗口属性
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)

        # --- 黑猫精灵动画器（含耳抖/尾摆/呼吸）---
        self._anim = SpriteAnimator(self.RES_DIR, display_width=340)
        self._iw = self._anim.width
        self._ih = self._anim.height
        self._anim.on_update = self.update
        self._anim.start()

        # --- TTS 语音引擎 ---
        self._tts = TTSEngine()
        self._tts.speak_started.connect(self._on_tts_started)
        self._tts.speak_finished.connect(self._on_tts_finished)

        # --- 整体弹跳偏移 ---
        self._anim_offset = QPoint(0, 0)
        self._anim_start = QElapsedTimer()
        self._anim_type = ""
        self._anim_duration = 300
        self._bounce_timer = QTimer(self)
        self._bounce_timer.timeout.connect(self._bounce_tick)
        self._bounce_timer.setInterval(16)

        # --- 说话嘴巴控制 ---
        self._talk_timer = QTimer(self)
        self._talk_timer.setInterval(80)
        self._talk_timer.timeout.connect(self._talk_tick)

        # --- 气泡 ---
        self._bubble_text = ""
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)

        # --- 鼠标 ---
        self._drag_pos = QPoint()
        self._is_drag = False

        # --- UI ---
        self._init_sub_widgets()
        self._init_tray()

        # --- 核心 ---
        self._status = StatusSystem(self)
        self._status.mood_changed.connect(self._on_mood_changed)
        self._status.start()

        self._hook = KeyboardHook(self)
        self._hook.key_pressed.connect(self._on_key)
        self._hook.start()

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(60000)
        self._save_timer.timeout.connect(self._save_state)
        self._save_timer.start()

        # --- 启动 ---
        self.setFixedSize(self._iw, self._ih)
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            self.move(int(g.width() * 0.7), int(g.height() * 0.4))
        self.show()
        self.raise_()
        self.activateWindow()
        self._force_top()
        self._click_count = 0

        self._load_state()

        QTimer.singleShot(200, self._force_top)
        # 黑猫启动问候（喵星语 + 傲娇）
        QTimer.singleShot(1500, lambda: self._say_with_expression(
            "喵～本喵来了，你最好是来喂我的。", "happy", "bounce"))

    # ==================== 子控件 ====================

    def _init_sub_widgets(self):
        self._bongo = BongoPanel(self)
        self._bongo.hide()
        self._bongo_on = False

    def _init_tray(self):
        self._tray = QSystemTrayIcon(self)
        # 托盘图标：用 idle 表情缩放
        icon_pm = QPixmap(32, 32)
        icon_pm.fill(Qt.transparent)
        ip = QPainter(icon_pm)
        ip.setRenderHint(QPainter.Antialiasing)
        idle_path = os.path.join(self.RES_DIR, 'expressions', 'idle_transparent.png')
        if not os.path.exists(idle_path):
            idle_path = os.path.join(self.RES_DIR, 'expressions', 'idle.png')
        if os.path.exists(idle_path):
            small = QPixmap(idle_path).scaled(
                28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ip.drawPixmap(2, 2, small)
        ip.end()
        self._tray.setIcon(QIcon(icon_pm))
        self._tray.setToolTip("黑猫桌宠")
        m = QMenu()
        m.addAction("显示/隐藏").triggered.connect(
            lambda: self.hide() if self.isVisible() else (self.show(), self._force_top()))
        m.addSeparator()
        m.addAction("退出").triggered.connect(self._quit)
        self._tray.setContextMenu(m)
        self._tray.show()

    # ==================== 绘制 ====================

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        ox, oy = self._anim_offset.x(), self._anim_offset.y()

        # 绘制黑猫
        self._anim.draw(p, ox, oy)

        # 对话气泡
        if self._bubble_text:
            self._draw_bubble(p)

    def _draw_bubble(self, p):
        font = QFont("Microsoft YaHei", 10)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self._bubble_text)
        bw = max(tw + 24, 60)
        bh = 28
        bx = (self._iw - bw) // 2
        by = 5

        # 气泡背景（黑猫主题：浅灰色背景，深色边框）
        path = QPainterPath()
        path.addRoundedRect(bx, by, bw, bh, 12, 12)
        p.fillPath(path, QColor(245, 245, 250, 240))
        pen = QPen(QColor(60, 60, 80, 220), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(bx, by, bw, bh, 12, 12)

        p.setPen(QColor(40, 40, 60))
        p.setFont(font)
        p.drawText(QRect(bx, by, bw, bh), Qt.AlignCenter, self._bubble_text)

    # ==================== 鼠标事件 ====================

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos()
            self._is_drag = False
            self.grabMouse()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            delta = e.globalPos() - self._drag_pos
            if delta.manhattanLength() > 3:
                self._is_drag = True
                self.move(self.pos() + delta)
                self._drag_pos = e.globalPos()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.releaseMouse()
            if not self._is_drag:
                self._click()
            self._is_drag = False

    def mouseDoubleClickEvent(self, e):
        self._click()

    def enterEvent(self, e):
        self.setCursor(Qt.PointingHandCursor)

    def leaveEvent(self, e):
        self.setCursor(Qt.ArrowCursor)

    # ==================== 右键 ====================

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: rgba(25,25,35,0.96); border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 10px; padding: 6px; color: white; font-size: 12px; }
            QMenu::item { padding: 7px 18px; border-radius: 6px; margin: 1px; }
            QMenu::item:hover { background: rgba(255,255,255,0.1); }
            QMenu::separator { height: 1px; background: rgba(255,255,255,0.05); margin: 4px 10px; }
        """)
        for k, info in ACTIONS.items():
            menu.addAction(f"{info.icon}  {info.label}").triggered.connect(
                lambda _, x=k: self._act(x))
        menu.addSeparator()
        expr_menu = menu.addMenu("表情切换")
        # 黑猫的6种表情
        for name, label in [("normal","趴着"), ("happy","开心"), ("sleepy","理毛"),
                             ("surprised","惊讶"), ("sad","警惕"), ("playful","坐着")]:
            expr_menu.addAction(label).triggered.connect(lambda _, n=name: self._anim.set_expression(n))
        menu.addSeparator()
        talk_menu = menu.addMenu("跟我说话")
        for scene, label in [("greeting","打招呼"), ("idle","闲聊"), ("tease","调皮"),
                             ("hungry","说饿了"), ("bye","告别")]:
            talk_menu.addAction(label).triggered.connect(lambda _, s=scene: self._say_scene(s))
        menu.addSeparator()
        menu.addAction("重置位置").triggered.connect(self._reset_pos)
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(self._quit)
        menu.exec_(e.globalPos())

    # ==================== 交互 ====================

    def _click(self):
        self._click_count += 1
        line = get_speech("click")
        self._say_with_expression(line.text, line.expression, "bounce")
        self._status.happy = min(100.0, self._status.happy + 3)
        QTimer.singleShot(3000, lambda: self._anim.update_mood(self._status.mood))

    def _say(self, text: str, expression: str = None, action: str = "none"):
        self._say_with_expression(text, expression, action)

    def _say_with_expression(self, text: str, expression: str = None, action: str = "none"):
        # 显示气泡
        self._bubble_text = text
        self._bubble_timer.start(4000)
        self.update()

        # 切换表情
        if expression and expression != "none":
            self._anim.set_expression(expression)

        # 触发动作
        if action == "bounce":
            self._anim.trigger_bounce()
            self._play_anim("bounce")
        elif action == "shake":
            self._play_anim("shake")

        # 播放 TTS 语音
        self._tts.speak(text)

    def _on_tts_started(self, text: str):
        self._talk_timer.start()
        self._talk_count = 0

    def _on_tts_finished(self):
        self._talk_timer.stop()
        self._anim.mouth_open = 0.0
        self.update()

    def _talk_tick(self):
        self._talk_count = getattr(self, '_talk_count', 0) + 1
        if self._tts.is_speaking:
            if self._talk_count % 3 < 2:
                self._anim.mouth_open = random.uniform(0.2, 0.6)
            else:
                self._anim.mouth_open = 0.1
        else:
            self._anim.mouth_open = 0.0
            self._talk_timer.stop()

    def _hide_bubble(self):
        self._bubble_text = ""
        self.update()

    def _say_scene(self, scene: str):
        line = get_speech(scene)
        self._say_with_expression(line.text, line.expression, line.action)

    def _on_mood_changed(self, mood: str):
        self._tray.setToolTip(f"黑猫桌宠 {mood}")
        self._anim.update_mood(mood)

    def _on_key(self, vk):
        self._bongo.press_key(vk)
        if not self._bongo_on:
            self._show_bongo()
        shortcuts = {0x31: 'feed', 0x32: 'play', 0x33: 'pet', 0x34: 'sleep', 0x35: 'dance'}
        if vk in shortcuts:
            self._act(shortcuts[vk])

    def _show_bongo(self):
        self._bongo_on = True
        self._bongo.move(max(0, (self._iw - self._bongo.width()) // 2),
                         self._ih)
        self._bongo.show()
        w = max(self._iw, self._bongo.width())
        self.setFixedSize(w, self._ih + self._bongo.height())

    def _act(self, name):
        a = get_action(name)
        scene_map = {
            'feed': 'feed', 'play': 'play', 'pet': 'pet',
            'sleep': 'sleep', 'dance': 'play'
        }
        scene = scene_map.get(name, 'idle')
        line = get_speech(scene)
        self._say_with_expression(line.text, line.expression, line.action)

        QTimer.singleShot(4000, lambda: self._anim.update_mood(self._status.mood))

        self._status.hunger = max(0, min(100, self._status.hunger + a.hunger_delta))
        self._status.happy = max(0, min(100, self._status.happy + a.happy_delta))
        self._status.energy = max(0, min(100, self._status.energy + a.energy_delta))
        self._status.sleeping = (name == 'sleep') and (not self._status.sleeping)

    # ==================== 整体弹跳 ====================

    def _play_anim(self, atype):
        self._anim_type = atype
        self._anim_start.start()
        if not self._bounce_timer.isActive():
            self._bounce_timer.start()

    def _bounce_tick(self):
        elapsed = self._anim_start.elapsed()
        if elapsed > self._anim_duration:
            self._anim_offset = QPoint(0, 0)
            self._bounce_timer.stop()
            self._anim_type = ""
            self.update()
            return
        t = elapsed / self._anim_duration
        if self._anim_type == "bounce":
            progress = math.sin(t * math.pi)
            y = -5 * progress
            self._anim_offset = QPoint(0, int(y))
        elif self._anim_type == "shake":
            amp = 4 * (1 - t)
            x = amp * math.sin(t * math.pi * 4)
            self._anim_offset = QPoint(int(x), 0)
        self.update()

    # ==================== 工具 ====================

    def _force_top(self):
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | 0x00000080)
        except Exception as e:
            pass

    def _reset_pos(self):
        scr = QApplication.primaryScreen()
        if scr:
            g = scr.geometry()
            self.move((g.width() - self.width()) // 2,
                     (g.height() - self.height()) // 2)
        self._say("喵～回到原位了。")

    def _load_state(self):
        self._status.set_all(**self._config.load_status())

    def _save_state(self):
        self._config.save_pos(self.x(), self.y())
        s = self._status.snapshot()
        self._config.save_status(s["hunger"], s["happy"], s["energy"])

    def _quit(self):
        self._save_state()
        self._tts.stop()
        self._anim.stop()
        self._hook.stop()
        self._status.stop()
        self._tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        self._save_state()
        self.hide()
        e.ignore()
