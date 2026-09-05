"""装备移动力/跳跃力词条接入物理：incSpeed/incJump 按比例放大走速与跳速，有封顶。"""

from __future__ import annotations

import pytest

from game import settings
from game.entities.player import Player
from game.systems.inventory import Item


class SpeedAssets:
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
    return Player(SpeedAssets(), 0.0, 0.0)


def _equip(**info) -> Item:
    info.setdefault("islot", "Cp")
    return Item(id="01002000", name="测试帽", kind="equip", info=info)


def test_no_bonus_keeps_base_speed(monkeypatch):
    p = make_player(monkeypatch)
    assert p.move_speed() == pytest.approx(settings.MOVE_SPEED)
    assert p.jump_velocity() == pytest.approx(settings.JUMP_VELOCITY)


def test_inc_speed_scales_move_speed(monkeypatch):
    """incSpeed 以 0.1 点为单位：+10 即 +1% 走速（WZ 30 = +3.0 速度）。"""
    p = make_player(monkeypatch)
    p.inventory.equipped["cape"] = _equip(incSpeed=10)
    assert p.move_speed() == pytest.approx(settings.MOVE_SPEED * 1.01)


def test_inc_jump_scales_jump_velocity(monkeypatch):
    p = make_player(monkeypatch)
    p.inventory.equipped["shoes"] = _equip(islot="So", incJump=20)
    assert p.jump_velocity() == pytest.approx(settings.JUMP_VELOCITY * 1.02)


def test_bonus_capped(monkeypatch):
    """词条堆到天上也只吃到封顶（+50%）。"""
    p = make_player(monkeypatch)
    p.inventory.equipped["cape"] = _equip(incSpeed=9999)
    cap = 1.0 + settings.EQUIP_SPEED_BONUS_CAP
    assert p.move_speed() == pytest.approx(settings.MOVE_SPEED * cap)
    assert p.jump_velocity() < 0   # 起跳速度保持向上为负的约定
