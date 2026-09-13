"""强化卷轴：官方 204 id 注册、WZ info 驱动的成功/加成、武器族匹配、旧 id 迁移。"""
from __future__ import annotations

from game import settings
from game.systems.inventory import Inventory, Item, make_item
from game.systems.scrolls import (apply_scroll, is_scroll_id,
                                  migrate_scroll_id, normalize_scroll_id,
                                  scroll_fee, scroll_of, scroll_stats,
                                  weapon_prefix)

_INFO_60 = {"success": 60, "incPAD": 2, "incSTR": 1}
_INFO_100 = {"success": 100, "incPAD": 5, "incSTR": 3, "incPDD": 1}


def _sword() -> Item:
    """合成一件可强化单手剑（01302000 → 武器族 130，tuc=7）。"""
    w = Item(id="01302000", name="木剑", kind="equip",
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


def test_scroll_success_adds_all_inc_stats_and_spends_tuc():
    """成功分支：WZ info 里的 inc* 固定值全部并入 extra、tuc−1、扣强化费。"""
    w = _sword()
    r = apply_scroll(scroll_of("02043001"), w, _AlwaysLow(),
                     level=10, meso=10000, info=_INFO_60)
    assert r["ok"] and r["charged"]
    assert w.extra["incPAD"] == 2 and w.extra["incSTR"] == 1
    assert w.tuc == 6
    assert r["meso"] == 10000 - scroll_fee(10)


def test_scroll_failure_keeps_item_but_spends_tuc():
    """失败分支：词条不变、tuc−1、装备不销毁。"""
    w = _sword()
    r = apply_scroll(scroll_of("02043001"), w, _AlwaysHigh(),
                     level=1, meso=10000, info=_INFO_60)
    assert not r["ok"] and r["charged"]
    assert w.extra == {}
    assert w.tuc == 6


def test_scroll_wrong_slot_returns_none():
    """栏位不符：返回 None，装备与次数不变。"""
    top = Item(id="01040000", name="上衣", kind="equip", info={"islot": "Ma"})
    assert apply_scroll(scroll_of("02043001"), top, _AlwaysLow(),
                        meso=9999, info=_INFO_60) is None
    assert top.tuc == 0 and top.extra == {}


def test_scroll_wrong_weapon_family_returns_none():
    """武器族不匹配：弓（145）不能用单手剑卷轴（130），返回 None。"""
    bow = Item(id="01452002", name="长弓", kind="equip",
               info={"islot": "WpSi"}, tuc=5)
    assert weapon_prefix(bow.id) == "145"
    assert apply_scroll(scroll_of("02043001"), bow, _AlwaysLow(),
                        meso=9999, info=_INFO_60) is None
    assert bow.tuc == 5 and bow.extra == {}


def test_scroll_vs_matching_family_succeeds():
    """同族武器（单手剑 130）可用对应卷轴。"""
    w = _sword()
    r = apply_scroll(scroll_of("02043001"), w, _AlwaysLow(),
                     meso=9999, info=_INFO_60)
    assert r is not None and r["ok"]


# ── 防具卷轴：统一由卷轴 id 类别推导目标栏位 ─────────────────────────
_CAPE_INFO = {"success": 60, "incMHP": 10}


def _cape() -> Item:
    """合成一件可强化披风（islot Sr → 栏位 cape，tuc=5）。"""
    c = Item(id="01102000", name="披风", kind="equip",
             info={"islot": "Sr"}, tuc=5)
    return c


def test_cape_hp_scroll_targets_cape_slot():
    """披风体力卷轴（02041007）：目标栏位 cape、incMHP 并入 extra。"""
    cape = _cape()
    scroll = scroll_of("02041007")
    assert scroll is not None and scroll["slot"] == "cape"
    r = apply_scroll(scroll, cape, _AlwaysLow(),
                     level=1, meso=10000, info=_CAPE_INFO)
    assert r["ok"] and cape.extra["incMHP"] == 10 and cape.tuc == 4


def test_cape_scroll_rejects_weapon_target():
    """披风卷轴对武器栏位无效：返回 None，不消耗。"""
    w = _sword()
    assert apply_scroll(scroll_of("02041007"), w, _AlwaysLow(),
                        meso=9999, info=_CAPE_INFO) is None
    assert w.tuc == 7 and w.extra == {}


def test_scroll_of_unsupported_category_is_none():
    """游戏未实现的栏位（项链 20412）识别为卷轴但无目标栏位，返回 None。"""
    assert scroll_of("02041201") is None


def test_scroll_tuc_exhausted_returns_none():
    """强化次数用完：返回 None。"""
    w = _sword()
    w.tuc = 0
    assert apply_scroll(scroll_of("02043001"), w, _AlwaysLow(),
                        meso=9999, info=_INFO_60) is None


def test_scroll_insufficient_meso_not_charged():
    """金币不足：不扣费、不耗次数、词条不变。"""
    w = _sword()
    r = apply_scroll(scroll_of("02043001"), w, _AlwaysLow(),
                     level=1, meso=0, info=_INFO_60)
    assert not r["ok"] and not r["charged"]
    assert w.tuc == 7 and w.extra == {}


def test_scroll_rejects_non_equip_target():
    """非装备目标：返回 None，不写 extra。"""
    fake = Item(id="02043001", name="卷轴", kind="consume",
                info={"islot": "WpSi"}, tuc=3)
    assert apply_scroll(scroll_of("02043001"), fake, _AlwaysLow(),
                        meso=9999, info=_INFO_60) is None
    assert fake.extra == {} and fake.tuc == 3


def test_scroll_fee_scales_with_level():
    """强化费随等级上涨：基础 + 每级增量。"""
    assert scroll_fee(1) == settings.SCROLL_FEE_BASE + settings.SCROLL_FEE_PER_LEVEL
    assert scroll_fee(10) == settings.SCROLL_FEE_BASE + 2000


def test_scroll_success_multiple_times_accumulates():
    """多次成功强化：词条累加、次数递减。"""
    w = _sword()
    for _ in range(3):
        apply_scroll(scroll_of("02043003"), w, _AlwaysLow(),
                     level=1, meso=99999, info=_INFO_100)
    assert w.extra["incPAD"] == 15 and w.extra["incSTR"] == 9
    assert w.tuc == 4


def test_scroll_stats_extracts_rate_and_incs():
    """scroll_stats：从 WZ info 提取成功率与 inc* 固定值，忽略其它字段。"""
    rate, incs = scroll_stats({"success": 30, "incPAD": 5, "incSTR": 3,
                               "price": 1, "cursed": 50})
    assert rate == 30 and incs == {"incPAD": 5, "incSTR": 3}
    assert scroll_stats(None) == (100, {})


def test_is_scroll_id_covers_all_official_204xxxx():
    """任意官方 204 段卷轴（含披风等防具）均识别；未登记段与旧 234 id 不算。"""
    assert is_scroll_id("02043001")            # 武器卷轴
    assert is_scroll_id("2043001")             # 7 位写法归一后命中
    assert is_scroll_id("02041007")            # 披风体力卷轴
    assert not is_scroll_id("02000000")
    assert not is_scroll_id("02340000")       # 旧自制 id：未迁移不算


def test_migrate_legacy_scroll_ids():
    """旧 234 段卷轴 id 迁移到官方单手剑档；官方卷轴归一 8 位；其余原样。"""
    assert migrate_scroll_id("02340000") == "02043001"
    assert migrate_scroll_id("02340001") == "02043005"
    assert migrate_scroll_id("02340002") == "02043003"
    assert migrate_scroll_id("2043001") == "02043001"   # 官方 7 位写法归一
    assert migrate_scroll_id("2000000") == "2000000"    # 非卷轴原样，不破坏存档键
    assert normalize_scroll_id("2043001") == "02043001"


def test_make_item_names_scroll_from_config_without_wz():
    """无 WZ 时卷轴名回退类别表兜底名（掉落/任务路径不显示「物品 id」）。"""
    it = make_item("2043001", None)
    assert it.id == "02043001"
    assert it.kind == "consume"
    assert it.name == "单手剑攻击卷轴 60%"


def test_stat_merges_extra():
    """stat() 读取时合并强化 extra 词条。"""
    w = _sword()
    w.info["incPAD"] = 10
    w.extra["incPAD"] = 3
    assert w.stat("incPAD") == 13
    assert w.stat("incSTR") == 0


def test_equip_extra_tuc_save_roundtrip():
    """强化词条与剩余次数经 to_dict/from_dict roundtrip 保真。"""
    inv = Inventory()
    w = _sword()
    w.extra["incPAD"] = 5
    w.tuc = 3
    inv.equipped["weapon"] = w
    inv.equips = [Item(id="01040000", name="帽", kind="equip")]

    d = inv.to_dict()
    assert d["equipped"]["weapon"]["extra"] == {"incPAD": 5}
    assert d["equipped"]["weapon"]["tuc"] == 3

    inv2 = Inventory.from_dict(d, assets=None)
    w2 = inv2.equipped["weapon"]
    assert w2.extra["incPAD"] == 5
    assert w2.tuc == 3
    assert w2.stat("incPAD") == 5


def test_from_dict_migrates_legacy_scroll_consumes():
    """旧档 consumes 里的 234 卷轴 id 在加载时迁移到官方 id。"""
    inv = Inventory.from_dict(
        {"consumes": {"02340000": 2}}, assets=None)
    assert inv.consumes["02043001"].count == 2
    assert "02340000" not in inv.consumes


def test_from_dict_accepts_old_plain_id_format():
    """旧档纯 id 格式（字符串）仍可加载。"""
    inv = Inventory.from_dict(
        {"equips": ["01040000"], "equipped": {"weapon": "01452002"}}, assets=None)
    assert inv.equips[0].id == "01040000"
    assert inv.equipped["weapon"].id == "01452002"
    assert inv.equipped["weapon"].extra == {}
    assert inv.equipped["weapon"].tuc == 0
