"""爬绳/爬梯：绳梯抓取范围与上下攀爬行为（合成数据，不依赖 WZ）。"""

from __future__ import annotations

import pytest

from game import settings
from game.core.physics import Physics
from game.entities.player import Player


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


ROPE = {"x": 450, "y1": 200, "y2": 454, "ladder": True}


def make():
    """梯子 200..454（底端贴近底地），底地 454、顶台 196：玩家 navel 站在两端地面时均能抓梯。"""
    return Physics(
        [fh(1, 0, 300, 454, 700, 454),
         fh(2, 1, 400, 196, 500, 196)],
        [dict(ROPE)], bounds={"left": 0, "top": 0, "right": 800, "bottom": 600})


class Keys:
    up = down = left = right = jump = attack = False


def _stub_init(self, assets, quest_defs=None):
    """最小初始化：只补 update 循环用到的状态字段，避免依赖 WZ。"""
    from game.systems.inventory import Inventory
    self.inventory = Inventory()
    self.skills = _StubSkills()
    self.quests = {}
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


class _StubSkills:
    def tick(self, dt):
        pass


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


def make_player(monkeypatch, ph: Physics, x: float, y: float) -> Player:
    """构造挂绳专用的 Player：桩掉动画/新档初始化，仅测攀爬状态机。"""
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _stub_init)
    return Player(StubAssets(), x, y)


def test_rope_at_detects_rope_from_bottom_ground():
    """站在梯底地面（navel = 地面 - FEET_OFFSET）时 rope_at 能命中梯子。"""
    ph = make()
    navel = 454 - settings.FEET_OFFSET
    r = ph.rope_at(ROPE["x"], navel)
    assert r is not None
    assert r["x"] == ROPE["x"]


def test_rope_at_detects_rope_from_top_ground():
    """站在梯顶平台（navel = 平台 - FEET_OFFSET，平台略高于绳顶）时 rope_at 能命中梯子。"""
    ph = make()
    navel = 196 - settings.FEET_OFFSET
    r = ph.rope_at(ROPE["x"], navel)
    assert r is not None
    assert r["x"] == ROPE["x"]


def test_rope_at_misses_rope_far_above_top():
    """远离绳身（明显高于顶检测范围）时不命中。"""
    ph = make()
    assert ph.rope_at(ROPE["x"], ROPE["y1"] - 80) is None


def test_climb_up_then_stay_on_top_platform(monkeypatch):
    """从梯底爬上梯顶落地后，持续按↑不重新挂绳（站立稳定，不振荡）。"""
    ph = make()
    p = make_player(monkeypatch, ph, ROPE["x"], 434)
    k = Keys()
    for _ in range(30):
        p.update(0.016, k, ph)
    assert p.on_ground is True
    k.up = True
    for _ in range(200):          # 足够多帧保证到顶 + 多帧站立
        p.update(0.016, k, ph)
    assert p.climbing is False
    assert p.on_ground is True
    assert p.y <= 176.0           # 落在顶平台（196 - FEET_OFFSET）附近


def test_climb_down_from_top_platform(monkeypatch):
    """站在梯顶平台按↓直接下滑；再按↓到梯底落地。"""
    ph = make()
    p = make_player(monkeypatch, ph, ROPE["x"], 196 - settings.FEET_OFFSET)
    k = Keys()
    for _ in range(30):
        p.update(0.016, k, ph)
    k.down = True
    for _ in range(60):
        p.update(0.016, k, ph)
    assert p.climbing is True
    assert p.y > 250.0            # 已下滑离开顶平台
    for _ in range(120):
        p.update(0.016, k, ph)
    assert p.climbing is False
    assert p.on_ground is True
