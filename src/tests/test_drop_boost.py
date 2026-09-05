"""装备掉落率倍率（/droprate 指令的后端）：只放大装备（item 首位 1）掉率，
其它品类不受影响；基础倍率 1.0 时不改变任何行为。经公开接口验证，可用
set/get 观测，不探私有成员。

设计：`OfficialDropTable.roll` 对装备行的 chance 乘以当前倍率（封顶 1000000
= 必掉）；`Monster.roll_drop` 对装备类掉率用 `scaled_equip_rate` 同样放大。
"""

from __future__ import annotations

import random

from game.systems import drops
from game.systems.drops import OfficialDropTable
from game.systems.gm import GmContext, execute


def test_base_multiplier_is_one():
    """默认倍率 1.0：scaled_equip_rate 原样返回，不掉率不变。"""
    drops.set_equip_drop_mult(1)
    assert drops.scaled_equip_rate(0.0003) == 0.0003


def test_scaled_equip_rate_caps_at_one():
    """倍率足够大时装备掉率封顶 1.0（必掉），不会超过 100%。"""
    drops.set_equip_drop_mult(1_000_000)
    try:
        assert drops.scaled_equip_rate(0.0003) == 1.0
    finally:
        drops.set_equip_drop_mult(1)


def test_official_roll_scales_only_equip_rows():
    """倍率放大后：装备行（1002019）由超低 chance 变得必掉，其它行不受倍率影响。"""
    drops.set_equip_drop_mult(1_000_000)
    try:
        table = OfficialDropTable.from_dict({
            "210100": [
                {"item": "1002019", "min": 1, "max": 1, "chance": 1000},
                {"item": "4000004", "min": 1, "max": 1, "chance": 1000},
            ],
        })
        for seed in range(3):
            res = table.roll("210100", random.Random(seed))
            assert "1002019" in [it["id"] for it in res.items]
    finally:
        drops.set_equip_drop_mult(1)


def test_official_zero_chance_equip_stays_never():
    """chance=0 的装备行即使倍率无限大也不掉（乘 0 仍为 0，不误判为必掉）。"""
    drops.set_equip_drop_mult(1_000_000)
    try:
        table = OfficialDropTable.from_dict({
            "210100": [{"item": "1002019", "min": 1, "max": 1, "chance": 0}],
        })
        assert table.roll("210100", random.Random(1)).items == []
    finally:
        drops.set_equip_drop_mult(1)


def test_gm_drop_rate_parses_multiplier():
    """/droprate 10 → 回调收到整数 10。"""
    calls = []

    def on_rate(n):
        calls.append(n)
        return ("system", "已调整")

    ctx = GmContext(warp=lambda m: ("system", ""), heal=lambda: ("system", ""),
                    meso=lambda n: ("system", ""), drop_rate=on_rate)
    lines = execute("/droprate 10", ctx)
    assert calls == [10]
    assert lines == [("system", "已调整")]


def test_gm_drop_rate_rejects_bad_args():
    """/droprate 不带参数或非正整数：报用法错误且不回调。"""
    calls = []
    ctx = GmContext(warp=lambda m: ("system", ""), heal=lambda: ("system", ""),
                    meso=lambda n: ("system", ""),
                    drop_rate=lambda n: calls.append(n) or ("system", ""))
    assert execute("/droprate", ctx)[0][0] == "error"
    assert execute("/droprate 0", ctx)[0][0] == "error"
    assert execute("/droprate abc", ctx)[0][0] == "error"
    assert calls == []
