"""地图边界缺口：走出最外侧地面边缘前的 vr 钳制区段没有 foothold，
会掉进「大缺口」坠出世界。回归 buglist#2。

修法：把可行走的 vr 水平边界收紧到最外侧非竖直 foothold 的边缘，
使玩家到边界即被挡住、无法走进无地面的边缝。
"""

from __future__ import annotations

import pytest

from game import settings
from game.core.physics import Physics, WallChain
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


# 地面 0..1000（含两端竖直墙 stub，模拟真实图边界 riser），
# 但 VR bounds 明显宽于地面（左右各溢出 ~50px）→ 边缝无地面。
MAP = [fh(1, 0, 0, 455, 500, 455, prev=0, next=2),
       fh(2, 0, 500, 455, 1000, 455, prev=1, next=3),
       fh(3, 0, 1000, 455, 1000, 480, prev=2, next=-1),   # 右墙 stub
       fh(0, 0, 0, 480, 0, 455, prev=-1, next=1)]          # 左墙 stub
BOUNDS = {"left": -60, "top": 0, "right": 1060, "bottom": 600}


def test_walkable_bounds_clamped_to_foothold_edges():
    """可行走 vr 边界应收紧到地面边缘 [0, 1000]，不覆盖无地面缝。"""
    ph = Physics(MAP, [], bounds=BOUNDS)
    r = settings.PLAYER_BODY_HALF_W
    assert ph.vr_left == pytest.approx(0.0)
    assert ph.vr_right == pytest.approx(1000.0)


def test_walk_left_to_edge_does_not_fall(monkeypatch):
    """贴地一路向左顶到边界：应停在左边缘、始终着地，不坠出。"""
    ph = Physics(MAP, [], bounds=BOUNDS)
    p = make_player(monkeypatch, 40.0, 455 - settings.FEET_OFFSET)
    k = Keys()
    k.left = True
    for _ in range(200):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    assert p.x == pytest.approx(0.0, abs=1.0)
    assert p.feet_y == pytest.approx(455.0, abs=2.0)


def test_walk_right_to_edge_does_not_fall(monkeypatch):
    """贴地一路向右顶到边界：应停在右边缘、始终着地，不坠出。"""
    ph = Physics(MAP, [], bounds=BOUNDS)
    p = make_player(monkeypatch, 960.0, 455 - settings.FEET_OFFSET)
    k = Keys()
    k.right = True
    for _ in range(200):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    assert p.x == pytest.approx(1000.0, abs=1.0)
    assert p.feet_y == pytest.approx(455.0, abs=2.0)
