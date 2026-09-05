"""怪物血条：受击后脚下出现、限时熄灭、再次受击刷新。"""

from __future__ import annotations

from game import settings
from game.entities.monster import Monster
from tests.test_monster import CHAIN, FakeAssets, make


def spawn():
    return Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                  "rx0": 0, "rx1": 450}, 0, make(CHAIN))


def step(mob, seconds: float, dt: float = 0.1) -> None:
    for _ in range(int(seconds / dt)):
        mob.update(dt, player_x=100000, player_y=0, mobs=[])


def test_hp_bar_hidden_until_hit():
    """没挨打的怪不显示血条。"""
    assert not spawn().hp_bar_visible


def test_hp_bar_shows_after_hit_and_expires():
    """受击点亮血条；静默超过时长后自动熄灭。"""
    mob = spawn()
    mob.take_hit(10)
    assert mob.hp_bar_visible
    step(mob, settings.MOB_HP_BAR_TTL + 0.2)
    assert not mob.hp_bar_visible


def test_hit_refreshes_hp_bar():
    """快到点时再受击：计时刷新，血条继续显示。"""
    mob = spawn()
    mob.take_hit(10)
    step(mob, settings.MOB_HP_BAR_TTL - 0.3)
    mob.take_hit(10)
    step(mob, 0.5)
    assert mob.hp_bar_visible
