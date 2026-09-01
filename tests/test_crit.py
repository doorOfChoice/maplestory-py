"""暴击：roll_damage 的 crit_rate 判定与 ×CRIT_MULT 结算（rng 注入固定值）。"""
from __future__ import annotations

import random

from game import settings
from game.stats import roll_damage


def test_crit_rate_100_always_crits():
    """crit_rate=100：任何随机种子都必暴击。"""
    for seed in (0, 1, 7, 42):
        dmg, crit = roll_damage(100, 1.0, 0, 0, random.Random(seed), crit_rate=100.0)
        assert crit is True
        assert dmg > 0


def test_crit_rate_0_never_crits():
    """crit_rate=0（默认）：绝不暴击。"""
    for seed in (0, 1, 7):
        dmg, crit = roll_damage(100, 1.0, 0, 0, random.Random(seed), crit_rate=0.0)
        assert crit is False


def test_crit_mid_rate_depends_on_rng():
    """crit_rate=50：rng 随机值决定是否暴击（<50% 命中、≥50% 落空）。"""
    dmg, crit = roll_damage(100, 1.0, 0, 0, random.Random(42), crit_rate=50.0)
    assert crit is True          # Random(42) 第 2 次 random()=0.025 < 0.5
    dmg, crit = roll_damage(100, 1.0, 0, 0, random.Random(0), crit_rate=50.0)
    assert crit is False         # Random(0) 第 2 次 random()=0.758 >= 0.5


def test_crit_damage_is_base_times_crit_mult():
    """同 rng 下暴击伤害 = 基础伤害 × CRIT_MULT（同 uniform 值）。"""
    base_dmg, _ = roll_damage(100, 1.0, 0, 0, random.Random(1), crit_rate=0.0)
    crit_dmg, crit = roll_damage(100, 1.0, 0, 0, random.Random(1), crit_rate=100.0)
    assert crit
    assert crit_dmg == int(base_dmg * settings.CRIT_MULT)


def test_crit_returns_two_values():
    """新签名返回 (伤害, 是否暴击) 二元组。"""
    result = roll_damage(100, 1.0, 0, 0, random.Random(7))
    assert isinstance(result, tuple) and len(result) == 2
