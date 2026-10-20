# -*- coding: utf-8 -*-
"""咕嘎企鹅精灵动画器 — 多表情图 + alpha 过渡 + 企鹅专属动作

表情: normal/happy/sleepy/surprised/sad/playful（5张素材，happy兼任normal）
动作: bounce(开心蹦) / shake(受惊抖) / point(指点江山-战棋军师)
      peek(偷偷看我) / tsundere(傲娇摇头)
"""
import math
import random
import os
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QRadialGradient


class SpriteAnimator:
    EXPRESSIONS = ["normal", "happy", "sleepy", "surprised", "sad", "playful"]

    FILE_MAP = {
        "normal":    "normal",
        "happy":     "happy",
        "sleepy":    "sleepy",
        "surprised": "surprised",
        "sad":       "sad",
        "playful":   "playful",
    }

    ACTIONS = ("none", "bounce", "shake", "point", "peek", "tsundere", "head_shake", "nod", "tilt", "wave")

    def __init__(self, res_dir: str, display_width: int = 260):
        self._res_dir = res_dir
        self._dw = display_width

        self._sprites = {}
        self._src_size = None
        for expr in self.EXPRESSIONS:
            file_key = self.FILE_MAP.get(expr, expr)
            paths = [
                os.path.join(res_dir, "expressions", f"{file_key}_transparent.png"),
                os.path.join(res_dir, "expressions", f"{file_key}.png"),
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
            raise FileNotFoundError(f"No penguin sprite images found in {res_dir}")
        if "normal" not in self._sprites:
            self._sprites["normal"] = self._sprites[list(self._sprites.keys())[0]]
        for expr in self.EXPRESSIONS:
            if expr not in self._sprites:
                self._sprites[expr] = self._sprites["normal"]

        ref_w, ref_h = self._src_size
        self._scale = display_width / ref_w
        ref_pm = self._sprites["normal"]
        ref_w = int(ref_pm.width() * self._scale)
        ref_h = int(ref_pm.height() * self._scale)
        self.width = ref_w
        self.height = ref_h
        self._dw, self._dh = ref_w, ref_h

        self._scaled = {}
        for expr, pm in self._sprites.items():
            scaled = pm.scaled(ref_w, ref_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

        self.expression = "normal"
        self._prev_expression = "normal"
        self._transition = 1.0
        self._transition_speed = 0.06

        # 企鹅动画参数
        self.breath_y = 0.0
        self.body_sway_x = 0.0        # 身体微摆
        self.wing_twitch = 0.0        # 翅膀抖动
        self.eye_open = 1.0
        self.body_squash = 1.0
        self.body_squash_target = 1.0
        self.mouth_open = 0.0

        # 动作叠加
        self.anim_rotate = 0.0
        self.anim_offset = QPointF(0, 0)
        self.anim_scale_x = 1.0
        self.anim_scale_y = 1.0
        self.action = "none"
        self._action_timer = 0.0
        self._action_phase = 0.0
        self._peek_side = 1
        self.head_yaw = self.head_nod = self.head_tilt = 0.0

        # 眨眼 / 翅膀抖
        self._blink_countdown = random.uniform(2.5, 6.0)
        self._blink_closing = False
        self._wing_twitch_countdown = random.uniform(3.0, 9.0)
        self._wing_twitch_active = False
        self._wing_twitch_duration = 0.0
        self._wing_twitch_phase = 0.0

        # 动画系统：关键帧轨道（驱动身体位移/挤压/旋转，不替换表情）
        # type=track: frames=[(dy, squash, rot)] 参数帧；type=frames: 真实图片帧（GIF表情包）
        self.clips = {}
        self._clip = None
        self._clip_frame = 0.0
        self._track_dy = 0.0
        self._track_squash = 1.0
        self._track_rot = 0.0
        self._build_tracks()
        self._load_stickers(os.path.join(res_dir, 'stickers'))

        # 常态表情来回切换
        self._idle_expr_countdown = random.uniform(4.0, 9.0)
        self._idle_expr_pick = None
        self._idle_expr_until = 0.0

        # 随机小动作（让企鹅"活"起来）
        self._idle_action_countdown = random.uniform(8.0, 16.0)

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
        if expr not in self.EXPRESSIONS or expr == self.expression:
            return
        self._prev_expression = self.expression
        self.expression = expr
        self._transition = 0.0

    def _set_expression_fast(self, expr: str):
        """立即切换表情（不做 blend）——用于说话时的口型闪烁"""
        if expr not in self.EXPRESSIONS or expr == self.expression:
            return
        self._prev_expression = self.expression
        self.expression = expr
        self._transition = 1.0

    def update_mood(self, mood_emoji: str):
        mapping = {
            '😄': 'happy', '😊': 'happy', '😴': 'sleepy',
            '😢': 'sad', '😕': 'sad',
        }
        self.set_expression(mapping.get(mood_emoji, 'normal'))

    def trigger_bounce(self):
        self.body_squash_target = 0.86

    def set_talking(self, talking: bool):
        pass

    # ==================== 动画关键帧轨道 ====================

    def _build_tracks(self):
        """身体动画轨道（只驱动位移/挤压/旋转，表情由 expression 决定）"""
        # (dy 位移, squash 挤压(1=正常), rot 旋转)
        self.clips['idle'] = {'type': 'track', 'loop': True, 'fps': 6.0,
                              'frames': [(-1, 1.02, 0), (-3, 1.0, 0), (-2, 0.985, 0), (-1, 1.0, 0)]}
        self.clips['talk'] = {'type': 'track', 'loop': True, 'fps': 8.0,
                              # 极轻微脉动（几乎不可见，仅示意"在说话"）
                              'frames': [(0, 1.0, 0), (-1, 1.006, 0), (0, 1.0, 0), (-1, 1.006, 0)]}
        self.clips['jump'] = {'type': 'track', 'loop': False, 'fps': 15.0,
                              'frames': [(0, 1.04, 0), (-8, 0.95, 0), (-14, 0.9, 0),
                                         (-8, 0.95, 0), (0, 1.0, 0), (2, 1.08, 0)]}
        self.clips['wave'] = {'type': 'track', 'loop': False, 'fps': 8.0,
                              'frames': [(0, 1.0, -6), (0, 1.0, 0), (0, 1.0, 6), (0, 1.0, 0)]}

    def play_clip(self, name, loop=None):
        if name not in self.clips:
            return
        if loop is not None:
            self.clips[name]['loop'] = loop
        self._clip = name
        self._clip_frame = 0.0

    def stop_clip(self):
        self._clip = None
        self._clip_frame = 0.0
        self._track_dy = 0.0
        self._track_squash = 1.0
        self._track_rot = 0.0

    @property
    def active_clip(self):
        return self._clip

    def _load_stickers(self, stickers_dir):
        """GIF 表情包 → 剪辑（名称为 sticker:<文件名>）"""
        if not os.path.isdir(stickers_dir):
            return
        try:
            from PIL import Image as PILImage
        except ImportError:
            return
        for f in sorted(os.listdir(stickers_dir)):
            if not f.lower().endswith('.gif'):
                continue
            try:
                im = PILImage.open(os.path.join(stickers_dir, f))
                frames = []
                idx = 0
                while True:
                    im.seek(idx)
                    frames.append(self._pil_to_pixmap(im.convert('RGBA')))
                    idx += 1
                    try:
                        im.seek(idx)
                    except EOFError:
                        break
                if frames:
                    self.clips[f'sticker:{os.path.splitext(f)[0]}'] = {
                        'type': 'frames', 'frames': frames, 'fps': 12.0, 'loop': True,
                    }
            except Exception:
                continue

    def _pil_to_pixmap(self, pil_img):
        from PyQt5.QtGui import QImage
        data = pil_img.tobytes('raw', 'RGBA')
        qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
        pm = QPixmap.fromImage(qimg)
        scale = min(self._dw / max(1, pm.width()), self._dh / max(1, pm.height()))
        return pm.scaled(int(pm.width() * scale), int(pm.height() * scale),
                         Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def play_sticker(self, name):
        self.play_clip(f'sticker:{name}')

    @property
    def sticker_names(self):
        return [n[8:] for n in self.clips if n.startswith('sticker:')]

    # ==================== 动作控制 ====================

    def trigger_action(self, action: str):
        from core.embodiment import ALIASES
        action=ALIASES.get(action,action)
        if action in self.ACTIONS and action != "none":
            self.action = action
            self._action_timer = 0.0
            self._action_phase = 0.0
            if action == "bounce":
                self.body_squash_target = 0.86
                self.play_clip('jump', loop=False)   # 跳跃真动画
            if action == "peek":
                self._peek_side = random.choice([-1, 1])

    def _tick(self):
        self.frame += 1
        t = self._time = self.frame / 30.0

        # ---- 呼吸（圆滚滚企鹅，起伏小）----
        breath = math.sin(t * 2 * math.pi / 4.0) * 0.75
        self.breath_y = -breath * 1.5

        # ---- 身体微摆 ----
        self.body_sway_x = math.sin(t * 0.7 + 0.4) * 1.1 + math.sin(t * 2.2 + 1.3) * 0.25

        # ---- 翅膀抖动 ----
        self._wing_twitch_countdown -= 1 / 30
        if self._wing_twitch_countdown <= 0 and not self._wing_twitch_active:
            self._wing_twitch_active = True
            self._wing_twitch_phase = 0.0
            self._wing_twitch_duration = random.uniform(0.25, 0.5)
            self._wing_twitch_countdown = random.uniform(5.0, 12.0)
        if self._wing_twitch_active:
            self._wing_twitch_phase += 1 / 30
            if self._wing_twitch_phase >= self._wing_twitch_duration:
                self._wing_twitch_active = False
                self.wing_twitch = 0.0
            else:
                env = math.sin(self._wing_twitch_phase / self._wing_twitch_duration * math.pi)
                self.wing_twitch = env * abs(math.sin(self._wing_twitch_phase * 26))

        # ---- 表情过渡 ----
        if self._transition < 1.0:
            t_ease = 1 - (1 - self._transition) ** 3
            self._transition = min(1.0, self._transition + self._transition_speed + t_ease * 0.02)

        # ---- 眨眼（normal/happy）----
        if self.expression in ("normal", "happy") and self._transition > 0.5:
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
                        self._blink_countdown = random.uniform(3.0, 8.0)
        else:
            self.eye_open = 1.0

        # ---- 身体挤压回弹 ----
        if self.body_squash < self.body_squash_target:
            self.body_squash = min(self.body_squash_target, self.body_squash + 0.03)
        elif self.body_squash > self.body_squash_target:
            self.body_squash = max(self.body_squash_target, self.body_squash - 0.025)
        if self.body_squash == self.body_squash_target and self.body_squash_target < 1.0:
            self.body_squash_target = 1.0

        # ---- 动作动画 ----
        self._tick_action()

        # ---- 动画剪辑帧推进 ----
        if self._clip is not None:
            c = self.clips[self._clip]
            self._clip_frame += 1 / 30 * c['fps']
            n = len(c['frames'])
            if self._clip_frame >= n:
                if c['loop']:
                    self._clip_frame %= n
                else:
                    self._clip = None
                    self._clip_frame = 0.0
            if c.get('type') == 'track':
                idx = min(int(self._clip_frame), n - 1)
                dy, sq, rt = c['frames'][idx]
                self._track_dy, self._track_squash, self._track_rot = dy, sq, rt
        else:
            self._track_dy = 0.0
            self._track_squash = 1.0
            self._track_rot = 0.0

        # 说话 → 表情动作完全不变，只保留极轻微的身体脉动（talk 轨道已调至几乎不可见）
        if self._clip is None:
            if self.mouth_open > 0.05:
                self.play_clip('talk', loop=True)
            elif self.action == 'none':
                self.play_clip('idle', loop=True)

        # ---- 常态表情来回切换（空闲时偶尔换脸再换回来）----
        if self.action == "none" and self.mouth_open <= 0.05:
            self._idle_expr_countdown -= 1 / 30
            if self._idle_expr_countdown <= 0:
                self._idle_expr_countdown = random.uniform(6.0, 14.0)
                self._idle_expr_pick = random.choice(['playful', 'surprised', 'happy'])
                self._idle_expr_until = self._time + random.uniform(1.0, 2.2)
            if self._time < self._idle_expr_until and self._idle_expr_pick:
                self.set_expression(self._idle_expr_pick)
            elif self.expression not in ('normal', 'happy') and self._transition >= 1.0:
                self.set_expression('happy')
                self._idle_expr_pick = None

        # ---- 随机小动作（让企鹅活起来）----
        if random.random() < 0.0008 and self.expression == "normal" and self.action == "none":
            self.set_expression("sleepy")
            QTimer.singleShot(random.randint(1800, 3800), lambda: self.set_expression("normal"))

        # 随机小动作：空闲时偶尔蹦一下/偷看（保持动态）
        if self.action == "none" and self.mouth_open <= 0.05 and self._clip in (None, 'idle'):
            self._idle_action_countdown -= 1 / 30
            if self._idle_action_countdown <= 0:
                self._idle_action_countdown = random.uniform(10.0, 22.0)
                r = random.random()
                if r < 0.45:
                    self.trigger_action('bounce')
                elif r < 0.60:
                    self.trigger_action('peek')
                elif r < 0.75:
                    self.trigger_action('tsundere')

        if self.on_update:
            self.on_update()

    def _tick_action(self):
        self._action_timer += 1 / 30
        self._action_phase += 1 / 30
        a = self.action
        self.anim_rotate = 0.0
        self.anim_offset = QPointF(0, 0)
        self.anim_scale_x = 1.0
        self.anim_scale_y = 1.0
        self._point_active = 0.0
        self.head_yaw = self.head_nod = self.head_tilt = 0.0

        if a == "none":
            return

        if a in ('head_shake','nod','tilt','wave'):
            duration=1.35
            phase=min(1,self._action_timer/duration)
            if phase>=1:
                self.action='none';return
            envelope=math.sin(math.pi*phase)**.7
            if a=='head_shake':self.head_yaw=math.sin(phase*math.pi*5)*envelope
            elif a=='nod':self.head_nod=math.sin(phase*math.pi*4)*envelope
            elif a=='tilt':self.head_tilt=envelope
            elif a=='wave':
                self.anim_rotate=3*math.sin(phase*math.pi*6)*envelope
                self.anim_offset=QPointF(0,-2*envelope)
            return

        if a == "bounce":
            if self._action_timer > 0.45:
                self.action = "none"
                return
            pr = math.sin(self._action_phase * math.pi / 0.45)
            self.anim_offset = QPointF(0, -9 * pr)
            return

        if a == "shake":
            if self._action_timer > 0.5:
                self.action = "none"
                return
            amp = 5 * (1 - self._action_timer / 0.5)
            self.anim_offset = QPointF(amp * math.sin(self._action_phase * math.pi * 5), 0)
            self.anim_rotate = 2 * math.sin(self._action_phase * math.pi * 5)
            return

        if a == "tsundere":  # 傲娇摇头：慢摆 + 昂头
            dur = 1.4
            if self._action_timer > dur:
                self.action = "none"
                return
            amp = 4.5 * math.sin(self._action_phase / dur * math.pi)
            self.anim_rotate = -2.5 + amp * math.sin(self._action_phase * math.pi * 2.2)
            self.anim_offset = QPointF(0, -1.5)
            return

        if a == "point":  # 指点江山：前倾 + 指点手臂
            dur = 1.6
            if self._action_timer > dur:
                self.action = "none"
                return
            env = math.sin(self._action_timer / dur * math.pi)
            self.anim_rotate = 5 * env
            self.anim_offset = QPointF(0, -2 * env)
            self._point_active = env
            return

        if a == "peek":  # 偷偷看我：轻轻侧移探头偷看（不歪斜不压扁）
            dur = 1.1
            if self._action_timer > dur:
                self.action = "none"
                return
            side = self._peek_side
            if self._action_timer < 0.3:
                k = self._action_timer / 0.3
            elif self._action_timer > dur - 0.3:
                k = (dur - self._action_timer) / 0.3
            else:
                k = 1.0
            # 只做轻微横移 + 2.5 度内小倾（像探头偷看），保持正常比例
            self.anim_scale_x = 1.0
            self.anim_scale_y = 1.0
            self.anim_offset = QPointF(side * self._dw * 0.12 * k, -self._dh * 0.03 * k)
            self.anim_rotate = side * 2.5 * k
            return

        self.action = "none"

    @property
    def point_active(self):
        return getattr(self, "_point_active", 0.0)

    # ==================== 绘制 ====================

    def draw(self, p: QPainter, x: int, y: int):
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.Antialiasing, True)

        self._draw_shadow(p, x, y)

        cx = x + self._dw / 2
        cy = y + self._dh / 2
        sx = 2 - self.body_squash
        sy = self.body_squash
        breath_scale = 1.0 + math.sin(self._time * 2 * math.pi / 4.0) * 0.005

        # 说话时轻微点头（增加真实感）
        talk_bob = self.mouth_open * 1.6

        p.translate(cx + self.anim_offset.x(), cy + self.breath_y + self.anim_offset.y()
                    + talk_bob + self._track_dy)
        p.rotate(self.body_sway_x * 0.25 + self.anim_rotate + self._track_rot)
        sq = self._track_squash
        p.scale(breath_scale * sx * self.anim_scale_x * (2 - sq),
                breath_scale * sy * self.anim_scale_y * sq)
        p.translate(-cx, -cy)

        # GIF 表情包（真实图片帧）优先绘制；轨道动画不替换表情
        if self._clip is not None and self.clips[self._clip].get('type') == 'frames':
            frames = self.clips[self._clip]['frames']
            if frames:
                idx = min(int(self._clip_frame), len(frames) - 1)
                pm = frames[idx]
                p.drawPixmap(int(x + (self._dw - pm.width()) / 2),
                             int(y + self._dh - pm.height()), pm)
                p.restore()
                return

        if self._transition < 1.0:
            old_pm = self._scaled.get(self._prev_expression, self._scaled["normal"])
            new_pm = self._scaled.get(self.expression, self._scaled["normal"])
            p.setOpacity(1.0 - self._transition)
            self._draw_sprite(p,x,y,old_pm)
            p.setOpacity(self._transition)
            self._draw_sprite(p,x,y,new_pm)
            p.setOpacity(1.0)
        else:
            self._draw_sprite(p,x,y,self._src)

        # 说话动嘴：原画自带嘴部，不再叠画（避免黑线），只保留轻微点头真实感

        # 指点江山手臂
        if self.action == "point" and self.point_active > 0.05:
            self._draw_pointing_arm(p, x, y)

        p.restore()

    def _draw_sprite(self,p,x,y,pm):
        if max(abs(self.head_yaw),abs(self.head_nod),abs(self.head_tilt))<.001:
            p.drawPixmap(x,y,pm);return
        # Continuous mesh warp: head moves, deformation fades through the neck,
        # and the lower body remains anchored. Uses the existing transparent art.
        width,height=pm.width(),pm.height()
        for row in range(0,height,2):
            ratio=row/height
            weight=1.0 if ratio<.39 else max(0,min(1,(.66-ratio)/.27))
            weight=weight*weight*(3-2*weight)
            if weight==0:
                p.drawPixmap(QRectF(x,y+row,width,height-row),pm,QRectF(0,row,width,height-row))
                break
            dx=self.head_yaw*width*.038*weight+self.head_tilt*(height*.34-row)*.10*weight
            dy=self.head_nod*height*.017*weight
            scale=1-.055*abs(self.head_yaw)*weight
            target=QRectF(x+dx+width*(1-scale)/2,y+row+dy,width*scale,min(3,height-row))
            p.drawPixmap(target,pm,QRectF(0,row,width,min(3,height-row)))

    def _draw_shadow(self, p: QPainter, ox: int, oy: int):
        dw, dh = self._dw, self._dh
        shadow_w = dw * 0.5
        shadow_h = 11
        shadow_x = ox + (dw - shadow_w) / 2
        shadow_y = oy + dh - 8
        grad = QRadialGradient(shadow_x + shadow_w / 2, shadow_y, shadow_w / 2)
        grad.setColorAt(0, QColor(0, 0, 0, 40))
        grad.setColorAt(0.6, QColor(0, 0, 0, 16))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QRectF(shadow_x, shadow_y - shadow_h / 2, shadow_w, shadow_h))

    def _draw_mouth(self, p: QPainter, ox: int, oy: int):
        """说话小嘴（脸部位置动嘴弧线）"""
        dw, dh = self._dw, self._dh
        mx = ox + dw * 0.50
        my = oy + dh * 0.66
        open_ = 1.0 + self.mouth_open * 3
        pen = QPen(QColor(40, 30, 30), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(mx - 6, my)
        path.quadTo(mx, my + open_, mx + 6, my)
        p.drawPath(path)

    def _draw_pointing_arm(self, p: QPainter, ox: int, oy: int):
        """指点江山：右侧伸出的指点手臂（黄手臂+小拳头+指向箭头）"""
        dw, dh = self._dw, self._dh
        env = self.point_active
        arm_x = ox + dw * 0.86
        arm_y = oy + dh * 0.42 + math.sin(self._action_phase * math.pi * 3) * 2.5 * env

        pen = QPen(QColor(245, 180, 60), 7)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(arm_x - 26, arm_y + 20)
        path.quadTo(arm_x - 8, arm_y + 6, arm_x, arm_y)
        p.drawPath(path)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(245, 190, 70))
        p.drawEllipse(QPointF(arm_x, arm_y), 10, 10)

        arrow = QPainterPath()
        arrow.moveTo(arm_x + 18, arm_y - 8)
        arrow.lineTo(arm_x + 18, arm_y + 8)
        arrow.lineTo(arm_x + 30, arm_y)
        arrow.closeSubpath()
        p.setBrush(QColor(255, 120, 60))
        p.drawPath(arrow)

    def _draw_blink_eyes(self, p: QPainter, ox: int, oy: int):
        dw, dh = self._dw, self._dh
        for fx in (0.40, 0.60):
            cx = ox + dw * fx
            cy = oy + dh * 0.48
            eye_w = dw * 0.07
            pen = QPen(QColor(20, 20, 25), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - eye_w / 2, cy)
            path.quadTo(cx, cy + 2.2, cx + eye_w / 2, cy)
            p.drawPath(path)
