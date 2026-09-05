"""强化卷轴：成功/失败分支（注入 rng）、强化费、装备 extra/tuc 存档 roundtrip。"""
from __future__ import annotations

from game import settings
from game.systems.inventory import Inventory, Item
from game.systems.scrolls import SCROLLS, apply_scroll, is_scroll_id, scroll_fee


def _weapon() -> Item:
    """合成一件可强化武器（islot 命中 weapon 栏位，tuc 由 make_item 同款初值）。"""
    w = Item(id="01452002", name="长弓", kind="equip",
             info={"islot": "WpSi", "tuc": 7})
    w.tuc = 7
    return w


class _AlwaysLow:
    """注入 rng：random() 恒 0 → 必然成功；randint 取区间下限。"""
    def random(self) -> float:
        return 0.0

    def randint(self, a, b) -> int:
        return a


class _AlwaysHigh:
    """注入 rng：random() 恒 0.99 → 必然失败。"""
    def random(self) -> float:
        return 0.99

    def randint(self, a, b) -> int:
        return a


def test_scroll_success_adds_extra_and_spends_tuc():
    """成功分支：extra 加区间下限、tuc−1、扣强化费。"""
    w = _weapon()
    r = apply_scroll(SCROLLS["02340000"], w, _AlwaysLow(), level=10, meso=10000)
    assert r["ok"] and r["charged"]
    assert w.extra["incPAD"] == 2
    assert w.tuc == 6
    assert r["meso"] == 10000 - scroll_fee(10)


def test_scroll_failure_keeps_item_but_spends_tuc():
    """失败分支：词条不变、tuc−1、装备不销毁。"""
    w = _weapon()
    r = apply_scroll(SCROLLS["02340000"], w, _AlwaysHigh(), level=1, meso=10000)
    assert not r["ok"] and r["charged"]
    assert w.extra == {}
    assert w.tuc == 6


def test_scroll_wrong_slot_returns_none():
    """栏位不符：返回 None，装备与次数不变。"""
    w = Item(id="01040000", name="上衣", kind="equip", info={"islot": "Ma"})
    assert apply_scroll(SCROLLS["02340000"], w, _AlwaysLow(), meso=9999) is None
    assert w.tuc == 0 and w.extra == {}


def test_scroll_tuc_exhausted_returns_none():
    """强化次数用完：返回 None。"""
    w = _weapon()
    w.tuc = 0
    assert apply_scroll(SCROLLS["02340000"], w, _AlwaysLow(), meso=9999) is None


def test_scroll_insufficient_meso_not_charged():
    """金币不足：不扣费、不耗次数、词条不变。"""
    w = _weapon()
    r = apply_scroll(SCROLLS["02340000"], w, _AlwaysLow(), level=1, meso=0)
    assert not r["ok"] and not r["charged"]
    assert w.tuc == 7 and w.extra == {}


def test_scroll_fee_scales_with_level():
    """强化费随等级上涨：基础 + 每级增量。"""
    assert scroll_fee(1) == settings.SCROLL_FEE_BASE + settings.SCROLL_FEE_PER_LEVEL
    assert scroll_fee(10) == settings.SCROLL_FEE_BASE + 2000


def test_scroll_success_multiple_times_accumulates():
    """多次成功强化：词条累加、次数递减。"""
    w = _weapon()
    for _ in range(3):
        apply_scroll(SCROLLS["02340002"], w, _AlwaysLow(), level=1, meso=99999)
    assert w.extra["incPAD"] == 3
    assert w.tuc == 4


def test_is_scroll_id():
    """卷轴 id 段识别（含 8 位补零形式）。"""
    assert is_scroll_id("02340000")
    assert is_scroll_id("2340000")
    assert not is_scroll_id("02000000")


def test_stat_merges_extra():
    """stat() 读取时合并强化 extra 词条。"""
    w = _weapon()
    w.info["incPAD"] = 10
    w.extra["incPAD"] = 3
    assert w.stat("incPAD") == 13
    assert w.stat("incSTR") == 0


def test_equip_extra_tuc_save_roundtrip():
    """强化词条与剩余次数经 to_dict/from_dict roundtrip 保真。"""
    inv = Inventory()
    w = _weapon()
    w.extra["incPAD"] = 5
    w.tuc = 3
    inv.equipped["weapon"] = w
    inv.equips = [Item(id="01040000", name="帽", kind="equip")]

    d = inv.to_dict()
    assert d["equipped"]["weapon"] == {"id": "01452002", "info": {"islot": "WpSi", "tuc": 7},
                                       "extra": {"incPAD": 5}, "tuc": 3}

    inv2 = Inventory.from_dict(d, assets=None)
    w2 = inv2.equipped["weapon"]
    assert w2.extra["incPAD"] == 5
    assert w2.tuc == 3
    assert w2.stat("incPAD") == 5


def test_from_dict_accepts_old_plain_id_format():
    """旧档纯 id 格式（字符串）仍可加载。"""
    inv = Inventory.from_dict(
        {"equips": ["01040000"], "equipped": {"weapon": "01452002"}}, assets=None)
    assert inv.equips[0].id == "01040000"
    assert inv.equipped["weapon"].id == "01452002"
    assert inv.equipped["weapon"].extra == {}
    assert inv.equipped["weapon"].tuc == 0
