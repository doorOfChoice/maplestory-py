"""装备词条键名映射：player 侧 bonus() 吃到 WZ 的 incSTR/incHP 等词条键。"""
from __future__ import annotations

from game.systems.inventory import Inventory, Item


def _equip(**info) -> Item:
    """合成一件可穿戴装备（词条用 WZ 的 inc 前缀键）。"""
    info.setdefault("islot", "WpSi")
    return Item(id="01452002", name="长弓", kind="equip", info=info)


def test_bonus_maps_inc_prefix_keys():
    """词条 bug 回归：bonus('str') 应读 WZ 的 incSTR 而非字面 'str' 键。"""
    inv = Inventory()
    inv.equipped["weapon"] = _equip(incSTR=5)
    assert inv.bonus("str") == 5


def test_bonus_covers_four_stats_and_vitals():
    """str/dex/int/luk/hp/mp 全部映射到对应 inc 词条。"""
    inv = Inventory()
    inv.equipped["weapon"] = _equip(incSTR=2, incDEX=3, incINT=4, incLUK=1,
                                    incHP=20, incMP=10)
    assert inv.bonus("str") == 2
    assert inv.bonus("dex") == 3
    assert inv.bonus("int") == 4
    assert inv.bonus("luk") == 1
    assert inv.bonus("hp") == 20
    assert inv.bonus("mp") == 10


def test_bonus_unchanged_for_incpad_style_keys():
    """直接传入 inc 前缀键（如 attack() 内部）仍按原样求和。"""
    inv = Inventory()
    inv.equipped["weapon"] = _equip(incPAD=25)
    assert inv.bonus("incPAD") == 25
    assert inv.attack() == 25


def test_bonus_no_equipment_is_zero():
    """无装备时任何词条求和为 0。"""
    assert Inventory().bonus("str") == 0
    assert Inventory().bonus("hp") == 0
