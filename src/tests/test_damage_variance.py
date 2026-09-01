"""伤害浮动：同一基础攻击力每次命中数值不同，且在 ±10% 范围内。"""
from __future__ import annotations

from game.systems.combat import roll_damage


def test_roll_damage_varies_within_range():
    vals = {roll_damage(100) for _ in range(300)}
    assert len(vals) > 1                      # 不再是固定值
    assert all(90 <= v <= 110 for v in vals)  # 波动不超过 ±10%


def test_roll_damage_never_below_one():
    assert all(roll_damage(b) >= 1 for b in (0, 1, 2) for _ in range(50))
