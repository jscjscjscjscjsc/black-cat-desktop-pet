# -*- coding: utf-8 -*-
"""黑猫精灵动画器 — 多表情图 + alpha blend 过渡 + 猫咪专属动作（耳抖/尾摆/呼吸）"""
import math
import random
import os
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QTransform


class SpriteAnimator:
    """基于多张表情图的黑猫精灵动画器

    特性：
    - 加载6种猫咪表情图（idle/sit/alert/happy/grooming/surprised）
    - 表情切换时 alpha blend 自然过渡
    - 趴着姿态的呼吸动画（极轻微上下浮动）
    - 尾巴摆动（subtle horizontal sway）
    - 随机耳抖（briefly transition idle→alert）
    - 眨眼（仅在 idle 表情上）
    - 点击弹跳反馈
    """

    # 黑猫的6种表情，对外仍用通用名（与话术系统对接）
    # 内部文件名映射到具体的猫咪姿态
    EXPRESSIONS = ["normal", "happy", "sleepy", "surprised", "sad", "playful"]

    # 通用名 → 猫咪姿态文件名
    FILE_MAP = {
        "normal":    "idle",       # 趴着（默认放松状态）
        "happy":     "happy",      # 闭眼侧躺幸福
        "sleepy":    "grooming",   # 理毛（慵懒）
        "surprised": "surprised",  # 警觉炸毛
        "sad":       "alert",      # 抬头警惕（替代"难过"）
        "playful":   "sit",        # 坐着看镜头
    }

    def __init__(self, res_dir: str, display_width: int = 260):
        self._res_dir = res_dir
        self._dw = display_width

        # 加载所有表情图
        self._sprites = {}
        self._src_size = None

        for expr in self.EXPRESSIONS:
            file_key = self.FILE_MAP.get(expr, expr)
            paths = [
                os.path.join(res_dir, "expressions", f"{file_key}_transparent.png"),
                os.path.join(res_dir, "expressions", f"{file_key}.png"),
                os.path.join(res_dir, f"{file_key}_transparent.png"),
                os.path.join(res_dir, f"{file_key}.png"),
            ]
            for path in paths:
                if os.path.exists(path):
                    pm = QPixmap(path)
                    if not pm.isNull():
                        self._sprites[expr] = pm
                        if self._src_size is None:
                            self._src_size = (pm.width(), pm.height())
                        break

        if not self._sprites:
            raise FileNotFoundError(f"No cat sprite images found in {res_dir}")

        # 确保有 normal 表情
        if "normal" not in self._sprites:
            first_key = list(self._sprites.keys())[0]
            self._sprites["normal"] = self._sprites[first_key]

        # 补全缺失的表情（用 normal 代替）
        for expr in self.EXPRESSIONS:
            if expr not in self._sprites:
                self._sprites[expr] = self._sprites["normal"]

        # 统一缩放尺寸
        ref_w, ref_h = self._src_size
        self._scale = display_width / ref_w
        ref_pm = self._sprites["normal"]
        ref_w = int(ref_pm.width() * self._scale)
        ref_h = int(ref_pm.height() * self._scale)
        self.width = ref_w
        self.height = ref_h
        self._dw = ref_w
        self._dh = ref_h

        # 预缩放所有表情图到统一显示尺寸
        self._scaled = {}
        for expr, pm in self._sprites.items():
            scaled = pm.scaled(
                ref_w, ref_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            canvas = QPixmap(ref_w, ref_h)
            canvas.fill(Qt.transparent)
            cp = QPainter(canvas)
            cp.setRenderHint(QPainter.SmoothPixmapTransform, True)
            x = (ref_w - scaled.width()) // 2
            y = (ref_h - scaled.height()) // 2
            cp.drawPixmap(x, y, scaled)
            cp.end()
            self._scaled[expr] = canvas

        # ---- 动画状态 ----
        self.frame = 0
        self._time = 0.0
        self.on_update = None

        # 当前表情
        self.expression = "normal"
        self._prev_expression = "normal"
        self._transition = 1.0
        self._transition_speed = 0.06

        # 动画参数（猫咪专用 — 趴着，动作幅度更小更优雅）
        self.breath_y = 0.0
        self.breath_scale = 1.0
        self.body_sway_x = 0.0  # 尾巴带动身体微摆
        self.ear_twitch = 0.0   # 耳抖幅度（0~1）
        self.eye_open = 1.0
        self.body_squash = 1.0
        self.body_squash_target = 1.0
        self.mouth_open = 0.0
        self.mouth_smile = 0.0

        # 眨眼
        self._blink_countdown = random.uniform(2.5, 6.0)
        self._blink_closing = False

        # 耳抖触发倒计时（猫咪会随机抖耳朵）
        self._ear_twitch_countdown = random.uniform(3.0, 8.0)
        self._ear_twitch_active = False
        self._ear_twitch_phase = 0.0

        # ---- 30fps 帧定时器 ----
        self._timer = QTimer()
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    @property
    def _src(self):
        return self._scaled.get(self.expression, self._scaled["normal"])

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def set_expression(self, expr: str):
        if expr not in self.EXPRESSIONS:
            return
        if expr == self.expression:
            return
        self._prev_expression = self.expression
        self.expression = expr
        self._transition = 0.0

    def update_mood(self, mood_emoji: str):
        mapping = {
            '😄': 'happy', '😊': 'normal', '😴': 'sleepy',
            '😢': 'sad', '😕': 'sad',
        }
        expr = mapping.get(mood_emoji, 'normal')
        self.set_expression(expr)

    def trigger_bounce(self):
        self.body_squash_target = 0.88  # 猫咪挤压幅度小一些

    def set_talking(self, talking: bool):
        pass

    # ==================== 动画循环 ====================

    def _tick(self):
        self.frame += 1
        t = self._time = self.frame / 30.0

        # ---- 呼吸（猫咪趴着，呼吸更慢更轻）----
        breath_1 = math.sin(t * 2 * math.pi / 4.5)
        breath_2 = math.sin(t * 2 * math.pi / 2.1 + 1.2) * 0.10
        breath = breath_1 * 0.75 + breath_2 * 0.25
        self.breath_y = -breath * 1.8  # 趴着的猫起伏很小
        self.breath_scale = 1.0 + breath * 0.006

        # ---- 尾巴摆动带动身体微摆 ----
        # 慢速大幅 + 快速小幅叠加，模拟尾巴在身后摆
        tail_slow = math.sin(t * 0.8 + 0.3) * 1.2
        tail_fast = math.sin(t * 2.4 + 1.5) * 0.3
        self.body_sway_x = tail_slow + tail_fast

        # ---- 耳朵抖动触发 ----
        self._ear_twitch_countdown -= 1 / 30
        if self._ear_twitch_countdown <= 0 and not self._ear_twitch_active:
            self._ear_twitch_active = True
            self._ear_twitch_phase = 0.0
            # 耳抖持续时间
            self._ear_twitch_duration = random.uniform(0.3, 0.6)
            # 下一次耳抖间隔
            self._ear_twitch_countdown = random.uniform(4.0, 12.0)

        if self._ear_twitch_active:
            self._ear_twitch_phase += 1 / 30
            if self._ear_twitch_phase >= self._ear_twitch_duration:
                self._ear_twitch_active = False
                self.ear_twitch = 0.0
            else:
                # 耳抖是高频小幅度震动
                phase = self._ear_twitch_phase / self._ear_twitch_duration
                envelope = math.sin(phase * math.pi)  # 0→1→0 包络
                self.ear_twitch = envelope * abs(math.sin(self._ear_twitch_phase * 30))

        # ---- 表情过渡（easeOutCubic 缓动）----
        if self._transition < 1.0:
            t_ease = 1 - (1 - self._transition) ** 3
            self._transition = min(1.0, self._transition + self._transition_speed + t_ease * 0.02)

        # ---- 眨眼（仅 normal 表情）----
        if self.expression == "normal" and self._transition > 0.5:
            self._blink_countdown -= 1 / 30
            if self._blink_countdown <= 0 and not self._blink_closing:
                self._blink_closing = True

            if self._blink_closing:
                self.eye_open -= 0.20
                if self.eye_open <= 0:
                    self.eye_open = 0
                    self._blink_closing = False
                    self._blink_countdown = -random.uniform(0.05, 0.15)
            else:
                if self._blink_countdown < 0:
                    self.eye_open = min(1.0, self.eye_open + random.uniform(0.12, 0.22))
                    if self.eye_open >= 1.0:
                        base = random.uniform(3.0, 8.0)  # 猫眨眼频率更低
                        if random.random() < 0.10:
                            base = 0.3
                        self._blink_countdown = base
        else:
            self.eye_open = 1.0

        # ---- 身体挤压（弹性缓动）----
        if self.body_squash < self.body_squash_target:
            self.body_squash = min(self.body_squash_target, self.body_squash + 0.03)
        elif self.body_squash > self.body_squash_target:
            self.body_squash = max(self.body_squash_target, self.body_squash - 0.025)
        if self.body_squash == self.body_squash_target and self.body_squash_target < 1.0:
            self.body_squash_target = 1.0

        # ---- 随机小动作（猫咪偶尔伸懒腰/理毛）----
        if random.random() < 0.0008 and self.expression == "normal":
            # 偶尔切换到理毛（sleepy）状态
            self.set_expression("sleepy")
            QTimer.singleShot(random.randint(2000, 4000), lambda: self.set_expression("normal"))

        if self.on_update:
            self.on_update()

    # ==================== 绘制 ====================

    def draw(self, p: QPainter, x: int, y: int):
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)

        # 底部阴影（柔和投影）
        self._draw_shadow(p, x, y)

        # 整体呼吸 + 挤压 + 尾巴摆动变换
        cx = x + self._dw / 2
        cy = y + self._dh / 2
        squash_x = 2 - self.body_squash
        squash_y = self.body_squash

        p.translate(cx, cy + self.breath_y)
        tail_rot = self.body_sway_x * 0.3
        p.rotate(tail_rot)
        p.scale(self.breath_scale * squash_x, self.breath_scale * squash_y)
        p.translate(-cx, -cy)

        if self._transition < 1.0:
            old_alpha = 1.0 - self._transition
            new_alpha = self._transition

            old_pm = self._scaled.get(self._prev_expression, self._scaled["normal"])
            new_pm = self._scaled.get(self.expression, self._scaled["normal"])

            p.setOpacity(old_alpha)
            p.drawPixmap(x, y, old_pm)

            p.setOpacity(new_alpha)
            p.drawPixmap(x, y, new_pm)

            p.setOpacity(1.0)
        else:
            p.drawPixmap(x, y, self._src)

        # ---- 睁眼时绘制眼睛高光（仅 normal 表情）----
        if (self.expression == "normal" and self._transition >= 1.0
                and self.eye_open > 0.7):
            self._draw_eye_shine(p, x, y)

        # ---- 胡须 ----
        if self.expression in ("normal", "happy", "playful") and self._transition >= 1.0:
            self._draw_whiskers(p, x, y)

        # ---- 耳抖叠加 ----
        if (self.expression == "normal" and self._transition >= 1.0
                and self.ear_twitch > 0.01):
            self._draw_ear_twitch(p, x, y)

        # ---- 眨眼叠加 ----
        if self.expression == "normal" and self._transition >= 1.0 and self.eye_open < 0.85:
            self._draw_blink_eyes(p, x, y)

        p.restore()

    def _draw_shadow(self, p: QPainter, ox: int, oy: int):
        """绘制猫咪底部柔和阴影"""
        dw = self._dw
        dh = self._dh
        shadow_y = oy + dh - 8
        shadow_w = dw * 0.55
        shadow_h = 12
        shadow_x = ox + (dw - shadow_w) / 2

        from PyQt5.QtGui import QRadialGradient
        grad = QRadialGradient(
            shadow_x + shadow_w / 2, shadow_y,
            shadow_w / 2
        )
        grad.setColorAt(0, QColor(0, 0, 0, 35))
        grad.setColorAt(0.6, QColor(0, 0, 0, 15))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QRectF(shadow_x, shadow_y - shadow_h/2, shadow_w, shadow_h))

    def _draw_eye_shine(self, p: QPainter, ox: int, oy: int):
        """绘制眼睛高光让猫咪更有神"""
        dw = self._dw
        dh = self._dh

        left_cx = ox + dw * 0.40
        left_cy = oy + dh * 0.42
        right_cx = ox + dw * 0.60
        right_cy = oy + dh * 0.42
        eye_w = dw * 0.08
        eye_h = eye_w * 1.15
        pupil_size = eye_w * 0.55

        for cx, cy in [(left_cx, left_cy), (right_cx, right_cy)]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawEllipse(QPointF(cx - eye_w*0.15, cy - eye_h*0.2),
                         pupil_size*0.3, pupil_size*0.3)
            p.setBrush(QColor(255, 255, 255, 120))
            p.drawEllipse(QPointF(cx + eye_w*0.2, cy + eye_h*0.1),
                         pupil_size*0.15, pupil_size*0.15)

    def _draw_whiskers(self, p: QPainter, ox: int, oy: int):
        """绘制猫咪胡须"""
        dw = self._dw
        dh = self._dh
        nose_x = ox + dw * 0.50
        nose_y = oy + dh * 0.53
        wlen = dw * 0.18

        pen = QPen(QColor(20, 20, 30, 40), 1.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # 左边胡须
        for i, dy in enumerate([-3, 0, 3]):
            path = QPainterPath()
            path.moveTo(nose_x - 4, nose_y + dy)
            angle = -0.15 + i * 0.15
            ex = nose_x - wlen
            ey = nose_y + dy + angle * wlen * 0.4
            ctrl_x = nose_x - wlen * 0.6
            ctrl_y = nose_y + dy - 1 + i * 0.5
            path.quadTo(ctrl_x, ctrl_y, ex, ey)
            p.drawPath(path)

        # 右边胡须
        for i, dy in enumerate([-3, 0, 3]):
            path = QPainterPath()
            path.moveTo(nose_x + 4, nose_y + dy)
            angle = -0.15 + i * 0.15
            ex = nose_x + wlen
            ey = nose_y + dy + angle * wlen * 0.4
            ctrl_x = nose_x + wlen * 0.6
            ctrl_y = nose_y + dy - 1 + i * 0.5
            path.quadTo(ctrl_x, ctrl_y, ex, ey)
            p.drawPath(path)

    def _draw_ear_twitch(self, p: QPainter, ox: int, oy: int):
        """在 normal 表情图上画耳抖叠加效果

        通过在耳朵位置叠加小的形变线条，模拟耳朵抖动
        """
        dw = self._dw
        dh = self._dh
        # 黑猫耳朵位置（约在头顶 y=20%-30%）
        # 左耳（约 x=32%, y=25%）
        left_ear_x = ox + dw * 0.32
        left_ear_y = oy + dh * 0.25
        # 右耳（约 x=68%, y=25%）
        right_ear_x = ox + dw * 0.68
        right_ear_y = oy + dh * 0.25

        # 耳抖时画几道小弧线表示耳朵在抖
        amp = self.ear_twitch * 3
        pen = QPen(QColor(20, 20, 30, int(self.ear_twitch * 120)), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # 左耳抖动线条
        for i in range(2):
            offset = amp * (i + 1) * 0.5
            path = QPainterPath()
            path.moveTo(left_ear_x - 4 - offset, left_ear_y + i * 2)
            path.quadTo(left_ear_x, left_ear_y - 2 - offset,
                       left_ear_x + 4 + offset, left_ear_y + i * 2)
            p.drawPath(path)

        # 右耳抖动线条（反相）
        for i in range(2):
            offset = amp * (i + 1) * 0.5
            path = QPainterPath()
            path.moveTo(right_ear_x - 4 - offset, right_ear_y + i * 2)
            path.quadTo(right_ear_x, right_ear_y + 2 + offset,
                       right_ear_x + 4 + offset, right_ear_y + i * 2)
            p.drawPath(path)

    def _draw_blink_eyes(self, p: QPainter, ox: int, oy: int):
        """在 normal 表情图上画闭眼弧线（眨眼）

        黑猫眼睛是金黄色大眼睛，眨眼时画一道弧线
        """
        dw = self._dw
        dh = self._dh

        # 黑猫眼睛位置（idle 趴着姿态，眼睛在头部偏上）
        # 左眼（约 x=40%, y=42%）
        left_cx = ox + dw * 0.40
        left_cy = oy + dh * 0.42
        eye_w = dw * 0.08

        # 右眼（约 x=60%, y=42%）
        right_cx = ox + dw * 0.60
        right_cy = oy + dh * 0.42

        if self.eye_open < 0.35:
            # 闭眼弧线（深色，描黑猫闭眼时的眼线）
            pen = QPen(QColor(15, 15, 20), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)

            for cx, cy in [(left_cx, left_cy), (right_cx, right_cy)]:
                path = QPainterPath()
                path.moveTo(cx - eye_w / 2, cy - 1)
                path.quadTo(cx, cy + 2, cx + eye_w / 2, cy - 1)
                p.drawPath(path)
