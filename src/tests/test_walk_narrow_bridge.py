"""窄桥接续段跨界回归：一帧步长跨过比自身还窄的中间段不应坠落。

真实案例 101010000 底部：宽段 #187 → 4px 窄桥 #188 → 略高的宽段 #172。
步速 300px/s、60fps = 5px/帧 > 4px，落点整个跳过 #188；修复前走右侧会
误判踩空、一路坠出地图。
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

    def passive_mods(self):
        return {}


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


BRIDGE = [fh(187, 0, -1485, 2150, -1461, 2150, prev=186, next=188),
          fh(188, 0, -1461, 2150, -1457, 2147, prev=187, next=172),
          fh(172, 0, -1457, 2147, -1404, 2148, prev=188, next=173),
          fh(173, 0, -1404, 2148, -900, 2148, prev=172, next=174)]


def test_walk_right_across_narrow_bridge_stays_grounded(monkeypatch):
    """从宽段向右走过 4px 窄桥：始终着地并落到桥后宽段（y≈2147）。"""
    ph = Physics(BRIDGE, [])
    p = make_player(monkeypatch, -1475.0, 2150 - settings.FEET_OFFSET)
    k = Keys()
    k.right = True
    for _ in range(40):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    assert p.x > -1457.0
    assert p.feet_y == pytest.approx(2147.0, abs=2.0)
