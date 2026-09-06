"""原版式水平响应：按方向键当帧满速、空中可瞬时反向、松手立停。"""

from __future__ import annotations

from types import SimpleNamespace

from game import settings
from game.core.physics import Physics
from game.entities.player import Player


class RespAssets:
    def equip_info(self, item_id: str) -> dict:
        return {}

    def consume_info(self, item_id: str) -> dict:
        return {}

    def item_name(self, item_id: str):
        return None

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)


def make_player(monkeypatch) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    return Player(RespAssets(), 0.0, 0.0)


def make_physics() -> Physics:
    seg = {"id": 1, "layer": 0, "platform": 0,
           "x1": -500, "y1": 100, "x2": 500, "y2": 100, "prev": -1, "next": -1}
    return Physics([seg], [])


def keys(left=False, right=False, up=False, down=False):
    return SimpleNamespace(left=left, right=right, up=up, down=down)


def ground(p: Player, ph: Physics) -> None:
    p.on_ground = True
    p.cur_fh = ph.by_id[1]
    p.y = 100.0 - settings.FEET_OFFSET
    p.vy = 0.0


def test_ground_key_press_reaches_full_speed_in_one_frame(monkeypatch):
    """地面按右一帧后 vx 即为满速：原版无起步缓动。"""
    p, ph = make_player(monkeypatch), make_physics()
    ground(p, ph)
    p.update(1 / 60, keys(right=True), ph)
    assert p.vx == settings.MOVE_SPEED


def test_air_turnaround_is_instant(monkeypatch):
    """空中从 +满速 按左键，单帧即反向满速：原版空中保留全部转向能力。"""
    p, ph = make_player(monkeypatch), make_physics()
    p.on_ground = False
    p.cur_fh = None
    p.x, p.y = 0.0, -200.0
    p.vx, p.vy = settings.MOVE_SPEED, -100.0
    p.update(1 / 60, keys(left=True), ph)
    assert p.vx == -settings.MOVE_SPEED


def test_releasing_keys_stops_in_one_frame(monkeypatch):
    """松手当帧即停：原版无滑行减速。"""
    p, ph = make_player(monkeypatch), make_physics()
    ground(p, ph)
    p.vx = settings.MOVE_SPEED
    p.update(1 / 60, keys(), ph)
    assert p.vx == 0.0
