"""掉落物落点：怪悬空（飞行怪）时掉落物应落到下方平台，而非停在半空。"""
from __future__ import annotations

import pytest

from game.systems.combat import Combat, DropItem


class FakeAssets:
    """两条水平平台：y=100 与 y=400，覆盖 x∈[0,200]。"""

    footholds = [
        {"id": 1, "layer": 0, "platform": 0, "x1": 0, "y1": 100,
         "x2": 200, "y2": 100, "prev": -1, "next": -1},
        {"id": 2, "layer": 0, "platform": 0, "x1": 0, "y1": 400,
         "x2": 200, "y2": 400, "prev": -1, "next": -1},
    ]

    def meso_frames(self, amount: int = 0):
        return []


def test_drop_ground_near_platform_uses_nearest():
    """怪贴着平台（±30px）时，落点取该平台。"""
    assert Combat(FakeAssets())._drop_ground(100.0, 110.0) == 100.0


def test_drop_ground_over_air_uses_platform_below():
    """怪悬在半空（附近无平台）时，落点取下方最近的平台。"""
    assert Combat(FakeAssets())._drop_ground(100.0, 250.0) == 400.0


def test_air_mob_drop_falls_to_platform():
    """悬空怪的掉落物受重力下落，最终停在下方平台，而不是悬空。"""
    c = Combat(FakeAssets())
    ground = c._drop_ground(100.0, 250.0)
    d = DropItem(100.0, 230.0, meso=10, ground_y=ground, assets=FakeAssets())
    c.drops.append(d)
    for _ in range(300):
        c.update(1 / 60.0, player=None)
    assert d.y == pytest.approx(400.0 - 4.0)
