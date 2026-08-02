# -*- coding: utf-8 -*-
"""黑猫互动动作定义"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Action:
    name: str
    label: str
    icon: str
    hunger_delta: float = 0
    happy_delta: float = 0
    energy_delta: float = 0
    mood_result: str = '😊'
    messages: List[str] = field(default_factory=list)
    animation: str = 'happy'


# 黑猫预定义动作（傲娇冷酷风格）
ACTIONS = {
    'feed': Action(
        name='feed', label='喂食', icon='🐟',
        hunger_delta=12, happy_delta=4, energy_delta=-2,
        mood_result='😊',
        messages=['喵...还行吧。', '哼，勉强能吃。', '下次要小鱼干。'],
        animation='happy',
    ),
    'play': Action(
        name='play', label='逗猫', icon='🪶',
        hunger_delta=-5, happy_delta=14, energy_delta=-8,
        mood_result='😄',
        messages=['喵！我要抓到它！', '别以为我会让你。', '哼，本喵 allow你陪我玩。'],
        animation='happy',
    ),
    'pet': Action(
        name='pet', label='摸摸', icon='✋',
        hunger_delta=0, happy_delta=8, energy_delta=-1,
        mood_result='🥰',
        messages=['呼噜呼噜...', '仅此一次。', '...不要停。'],
        animation='pet',
    ),
    'sleep': Action(
        name='sleep', label='打盹', icon='🌙',
        hunger_delta=-3, happy_delta=2, energy_delta=20,
        mood_result='😴',
        messages=['喵...困了。', '别吵我。', '呼噜呼噜...'],
        animation='sad',
    ),
    'dance': Action(
        name='dance', label='伸懒腰', icon='🐈',
        hunger_delta=-4, happy_delta=10, energy_delta=-6,
        mood_result='😄',
        messages=['喵～舒展一下。', '看本喵的身段。', '哼，优雅。'],
        animation='happy',
    ),
}


def get_action(name: str) -> Action:
    return ACTIONS.get(name, ACTIONS['play'])
