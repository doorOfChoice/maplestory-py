"""怪物接触伤害应使用自身 weaponAttack（带浮动），而非全局固定常量。"""
from __future__ import annotations

import pygame

from game import settings
from game.entities.monster import Monster
from game.core.physics import Physics
from tests.test_monster import FakeAssets, fh, make


def test_contact_hit_uses_own_attack_power():
    """FakeAssets 的 weaponAttack=10：接触伤害应落在 10±10%，而不是常量 8。"""
    ph = make([fh(1, 0, 0, 0, 300, 0)])
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 100, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 300}, 0, ph)
    hits: list = []
    mob.update(0.05, player_x=mob.x + 5,
               player_y=mob.cy - settings.FEET_OFFSET, mobs=hits)
    assert hits
    assert 9 <= hits[0]["amount"] <= 11
