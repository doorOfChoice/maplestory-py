"""暴击：roll_damage 的 crit_rate 判定与 ×crit_mult 结算（rng 注入固定值）。"""
from __future__ import annotations

import random

from game import settings
from game.stats import roll_damage


# 攻击区间 (lo, hi)：命中 100（无怪防、无等级差）
LO, HI = 100, 100


def test_crit_rate_100_always_crits():
    """crit_rate=100：任何随机种子都必暴击。"""
    for seed in (0, 1, 7, 42):
        dmg, crit = roll_damage(LO, HI, 1.0, 0, 0, 0,
                                random.Random(seed), crit_rate=100.0)
        assert crit is True
        assert dmg > 0


def test_crit_rate_0_never_crits():
    """crit_rate=0（默认）：绝不暴击。"""
    for seed in (0, 1, 7):
        dmg, crit = roll_damage(LO, HI, 1.0, 0, 0, 0,
                                random.Random(seed), crit_rate=0.0)
        assert crit is False


def test_crit_mid_rate_depends_on_rng():
    """crit_rate=50：rng 随机值决定是否暴击。"""
    dmg, crit = roll_damage(LO, HI, 1.0, 0, 0, 0,
                            random.Random(42), crit_rate=50.0)
    assert crit is True          # 第 2 次 random() < 0.5
    dmg, crit = roll_damage(LO, HI, 1.0, 0, 0, 0,
                            random.Random(0), crit_rate=50.0)
    assert crit is False         # 第 2 次 random() >= 0.5


def test_crit_mid_rate_depends_on_crit_mult():
    """同 rng 下暴击伤害 = 基础伤害 × crit_mult（crit_mult 可注入）。"""
    base_dmg, _ = roll_damage(LO, HI, 1.0, 0, 0, 0,
                              random.Random(1), crit_rate=0.0)
    crit_dmg, crit = roll_damage(LO, HI, 1.0, 0, 0, 0,
                                 random.Random(1), crit_rate=100.0,
                                 crit_mult=2.0)
    assert crit
    assert crit_dmg == int(base_dmg * 2.0)


def test_crit_default_uses_settings_crit_mult():
    """crit_mult 缺省用 settings.CRIT_MULT。"""
    base_dmg, _ = roll_damage(LO, HI, 1.0, 0, 0, 0,
                              random.Random(1), crit_rate=0.0)
    crit_dmg, _ = roll_damage(LO, HI, 1.0, 0, 0, 0,
                              random.Random(1), crit_rate=100.0)
    assert crit_dmg == int(base_dmg * settings.CRIT_MULT)


def test_crit_returns_two_values():
    """新签名返回 (伤害, 是否暴击) 二元组。"""
    result = roll_damage(LO, HI, 1.0, 0, 0, 0, random.Random(7))
    assert isinstance(result, tuple) and len(result) == 2
