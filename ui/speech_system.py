# -*- coding: utf-8 -*-
"""黑猫话术系统 — 喵星语 + 人类语言混合，傲娇冷酷风格

每条话术包含:
- text: 说的内容（喵星语 + 人类语言混合）
- expression: 对应的表情
- action: 触发的动作 (bounce/shake/none)
"""
import random


class SpeechLine:
    """单条话术"""
    __slots__ = ('text', 'expression', 'action')

    def __init__(self, text: str, expression: str = "normal", action: str = "none"):
        self.text = text
        self.expression = expression
        self.action = action


# ==================== 黑猫话术库 ====================
# 喵星语 + 人类语言混合，傲娇冷酷风格
# 称呼"铲屎官"或"两脚兽"代替"主人"

SPEECHES = {
    # ---- 日常问候 ----
    "greeting": [
        SpeechLine("喵...你来了啊。", "normal", "none"),
        SpeechLine("喵呜～本喵等你很久了，别误会，只是刚好趴在这。", "happy", "bounce"),
        SpeechLine("哼，喵～终于想起来喂我了？", "normal", "none"),
        SpeechLine("喵～看什么看，没见过这么帅的猫？", "playful", "bounce"),
        SpeechLine("喵呜...你又来打扰我睡觉。", "sleepy", "none"),
    ],

    # ---- 点击互动 ----
    "click": [
        SpeechLine("喵！别乱摸。", "surprised", "shake"),
        SpeechLine("喵呜～勉为其难让你摸一下。", "happy", "none"),
        SpeechLine("哼，喵～你手好凉。", "normal", "none"),
        SpeechLine("喵！我警告你，别碰我尾巴。", "surprised", "shake"),
        SpeechLine("喵呜～...再摸一会儿也可以。", "happy", "bounce"),
        SpeechLine("喵～你是真的很烦耶。", "playful", "none"),
    ],

    # ---- 喂食 ----
    "feed": [
        SpeechLine("喵～小鱼干！还行，算你识相。", "happy", "bounce"),
        SpeechLine("喵呜～本喵勉为其难吃一点。", "happy", "none"),
        SpeechLine("喵？就这？我要更好的。", "playful", "none"),
        SpeechLine("喵～下次要金枪鱼的，记住了。", "happy", "none"),
    ],

    # ---- 玩耍 ----
    "play": [
        SpeechLine("喵！羽毛棒？本喵来了！", "surprised", "bounce"),
        SpeechLine("喵呜～别以为我会让你，哼。", "playful", "bounce"),
        SpeechLine("喵～抓到了！看本喵身手。", "happy", "bounce"),
        SpeechLine("喵呜～再玩一会儿，仅此一次。", "playful", "none"),
    ],

    # ---- 摸头 ----
    "pet": [
        SpeechLine("呼噜呼噜...喵～", "happy", "none"),
        SpeechLine("喵呜～...还行，不要停。", "happy", "none"),
        SpeechLine("呼噜呼噜...喵～本喵允许了。", "sleepy", "none"),
        SpeechLine("喵～仅此一次，下不为例。", "normal", "none"),
    ],

    # ---- 睡觉 ----
    "sleep": [
        SpeechLine("喵呜～困了，别吵我。", "sleepy", "none"),
        SpeechLine("呼噜呼噜...喵～本喵要睡了。", "sleepy", "none"),
        SpeechLine("喵～帮我把灯关了。", "sleepy", "none"),
        SpeechLine("喵呜～谁也别想叫醒我。", "sleepy", "none"),
    ],

    # ---- 饿了 ----
    "hungry": [
        SpeechLine("喵...我饿了，你看着办。", "sad", "none"),
        SpeechLine("喵呜～怎么还没开饭？", "sad", "none"),
        SpeechLine("喵～本喵命令你，立刻上菜。", "playful", "none"),
        SpeechLine("喵...再不喂我，我就拆家。", "sad", "shake"),
    ],

    # ---- 难过/被冷落 ----
    "sad": [
        SpeechLine("喵...你是不是有别的猫了？", "sad", "none"),
        SpeechLine("喵呜～你都多久没陪我了。", "sad", "none"),
        SpeechLine("喵...本喵很寂寞你懂吗？", "sad", "none"),
        SpeechLine("喵呜～算了，反正你也不在意。", "sleepy", "none"),
    ],

    # ---- 惊讶 ----
    "surprised": [
        SpeechLine("喵？！你吓到我了！", "surprised", "shake"),
        SpeechLine("喵呜！怎么突然出现！", "surprised", "shake"),
        SpeechLine("喵？！什么声音？！", "surprised", "shake"),
        SpeechLine("喵呜～你走路没声音的吗？", "surprised", "bounce"),
    ],

    # ---- 调皮 ----
    "tease": [
        SpeechLine("喵～你以为你能抓到我？", "playful", "bounce"),
        SpeechLine("喵呜～本喵才不告诉你我在想什么。", "playful", "none"),
        SpeechLine("喵～哼，你上当了。", "playful", "bounce"),
        SpeechLine("喵呜～本喵的智商你无法理解。", "playful", "none"),
    ],

    # ---- 告别 ----
    "bye": [
        SpeechLine("喵～走了？记得早点回来喂我。", "sleepy", "none"),
        SpeechLine("喵呜～别太久，本喵会想...才怪。", "normal", "none"),
        SpeechLine("喵～路上小心，反正你也笨。", "playful", "none"),
        SpeechLine("喵呜～我睡觉了，你随便。", "sleepy", "none"),
    ],

    # ---- 闲聊/待机 ----
    "idle": [
        SpeechLine("喵～你在忙什么呢，两脚兽？", "normal", "none"),
        SpeechLine("喵呜～本喵 today 很无聊。", "playful", "none"),
        SpeechLine("喵～这世界除了我，还有谁可爱？", "playful", "none"),
        SpeechLine("喵呜～要不要本喵允许你摸我？", "happy", "bounce"),
        SpeechLine("喵～你看我干嘛？我都没看你。", "normal", "none"),
        SpeechLine("喵呜～今天太阳不错，适合睡觉。", "sleepy", "none"),
        SpeechLine("喵～本喵命令你，别玩手机了。", "playful", "none"),
        SpeechLine("喵呜～你存在的意义就是伺候本喵。", "playful", "bounce"),
    ],
}


def get_speech(scene: str) -> SpeechLine:
    """随机获取某个场景的话术"""
    lines = SPEECHES.get(scene, SPEECHES["idle"])
    return random.choice(lines)


def get_random_speech() -> SpeechLine:
    """随机获取任意场景的话术"""
    all_lines = []
    for lines in SPEECHES.values():
        all_lines.extend(lines)
    return random.choice(all_lines)
