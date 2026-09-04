"""斜坡上被怪物击退：横向位移把脚侧移插入坡面时，仍应落回坡面而不是坠出地面。

回归 buglist#1（在斜坡上被打会掉出地面）：击退给横向速度 + 小跳，
落地判定若只按当前 x 的垂直穿线，上坡方向受击时坡面抬升快过下落 → 永漏判。
"""

from __future__ import annotations

import pytest

from game import settings
from game.core.physics import Physics
from game.entities.player import Player


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


class Keys:
    up = down = left = right = jump = attack = False


class _StubSkills:
    def tick(self, dt):
        pass


def _stub_init(self, assets, quest_defs=None):
    from game.systems.inventory import Inventory
    self.inventory = Inventory()
    self.skills = _StubSkills()
    self.quests = {}
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


class StubAssets:
    def __init__(self):
        self.equips = None
        self.job = 0

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def make_player(monkeypatch, x: float, y: float) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _stub_init)
    return Player(StubAssets(), x, y)


BOUNDS = {"left": -2000, "top": -2000, "right": 2000, "bottom": 2000}


def test_hurt_into_uphill_slope_relands_on_slope(monkeypatch):
    """站在坡上被朝上坡方向击退：小跳落回后应贴回坡面，不坠出地面。"""
    ph = Physics([fh(1, 0, 0, 600, 800, -200)], [], bounds=BOUNDS)  # 45°上坡
    slope = ph.by_id[1]
    x0 = 400.0
    p = make_player(monkeypatch, x0, slope.y_at(x0) - settings.FEET_OFFSET)
    k = Keys()
    for _ in range(5):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    assert p.hurt(x0 - 100.0)          # 怪在左侧 → 向右（上坡方向）击退
    for _ in range(90):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    assert p.feet_y == pytest.approx(slope.y_at(p.x), abs=2.0)
    assert p.x == pytest.approx(x0, abs=120.0)  # 只在击退滑行范围内


def test_hurt_into_downhill_slope_relands_on_slope(monkeypatch):
    """对称情形：被朝下坡方向击退同样应落回坡面。"""
    ph = Physics([fh(1, 0, 0, 600, 800, -200)], [], bounds=BOUNDS)
    slope = ph.by_id[1]
    x0 = 400.0
    p = make_player(monkeypatch, x0, slope.y_at(x0) - settings.FEET_OFFSET)
    k = Keys()
    for _ in range(5):
        p.update(0.016, k, ph)
    assert p.hurt(x0 + 100.0)          # 怪在右侧 → 向左（下坡方向）击退
    for _ in range(90):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    assert p.feet_y == pytest.approx(slope.y_at(p.x), abs=2.0)
