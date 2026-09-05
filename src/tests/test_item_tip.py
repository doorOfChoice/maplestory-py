"""装备 tooltip 纯构建器：原版分段（名称/交换性/大数字/REQ/职业/分类/词条/tuc/介绍）。"""

from __future__ import annotations

from game.core import item_tip
from game.systems.inventory import Item


def make_item(name="测试剑", tuc=5, **info) -> Item:
    info.setdefault("islot", "WpSs")
    return Item(id="01302000", name=name, kind="equip", info=info, tuc=tuc)


def tip_for(item, level=10, stats=None, job=1000, desc=""):
    stats = stats or {"str": 20, "dex": 20, "int": 20, "luk": 20}
    return item_tip.build_item_tip(item, level, stats, job, desc=desc)


def hero(tip, label):
    for h in tip.heroes:
        if h.label == label:
            return h
    return None


def stat_row(tip, label):
    for s in tip.stats:
        if s.label == label:
            return s
    return None


def test_tip_title_and_category():
    """首字段为名称，装备分类为栏位名。"""
    tip = tip_for(make_item(name="木剑"))
    assert tip.name == "木剑"
    assert tip.category == "武器"


def test_tip_req_level_red_when_short():
    """需求等级不足标红，够级为普通色。"""
    item = make_item(reqLevel=30)
    short = tip_for(item, level=10)
    assert short.req_level == 30 and short.req_level_ok is False
    ok = tip_for(item, level=30)
    assert ok.req_level_ok is True


def test_tip_req_stats_only_nonzero_and_red():
    """REQ 四维只列非零项，不足标红。"""
    item = make_item(reqSTR=50, reqDEX=0)
    tip = tip_for(item, stats={"str": 20, "dex": 20, "int": 20, "luk": 20})
    assert len(tip.req_stats) == 1
    req = tip.req_stats[0]
    assert (req.key, req.need, req.ok) == ("STR", 50, False)


def test_tip_job_line_highlight():
    """职业可穿：reqJob 位掩码决定高亮，0 为全职业。"""
    tip = tip_for(make_item(reqJob=1))          # 战士
    jobs = dict((name, ok) for name, ok in tip.jobs)
    assert jobs["战士"] is True and jobs["魔法师"] is False
    all_ok = tip_for(make_item(reqJob=0))
    assert all(ok for _name, ok in all_ok.jobs)


def test_tip_attack_big_number():
    """武器攻击力大数字：incPAD 汇总（基础+强化）。"""
    item = make_item(incPAD=50)
    item.extra["incPAD"] = 3
    tip = tip_for(item)
    h = hero(tip, "攻击力提升")
    assert h is not None and h.value == 53


def test_tip_scroll_extra_note_green_suffix():
    """强化附加部分单独记录，视图层标绿 (+N)。"""
    item = make_item(incPAD=50, incSTR=4)
    item.extra["incSTR"] = 2
    tip = tip_for(item)
    row = stat_row(tip, "力量")
    assert row is not None and row.total == 6 and row.extra == 2


def test_tip_full_stat_rows():
    """完整词条行：HP/MP/速度/跳跃按 WZ 键取值。"""
    item = make_item(incMHP=30, incMMP=20, incSpeed=15, incJump=2,
                     incACC=15, incEVA=20, incMDD=7)
    tip = tip_for(item)
    assert stat_row(tip, "最大血量").total == 30
    assert stat_row(tip, "最大魔量").total == 20
    assert stat_row(tip, "速度").total == 15 and stat_row(tip, "速度").tenth
    assert stat_row(tip, "跳跃").total == 2 and stat_row(tip, "跳跃").tenth
    assert stat_row(tip, "命中").total == 15
    assert stat_row(tip, "回避").total == 20
    assert stat_row(tip, "魔防").total == 7


def test_tip_tuc_only_cash_and_trade_flags():
    """可升级次数 / 固有 / 商城 / 不可交换标记。"""
    assert tip_for(make_item(tuc=5)).tuc == 5
    tip = tip_for(make_item(only=1, tradeBlock=1))
    assert "固有装备物品" in tip.flags and "不可交换" in tip.flags
    assert "商城物品" in tip_for(make_item(cash=1)).flags


def test_tip_desc_and_hint_appended():
    """String.wz 介绍与悬停提示写入 note。"""
    tip = tip_for(make_item(), desc="一把朴素的剑。")
    assert "一把朴素的剑。" in tip.note
    joined = item_tip.tip_with_note(tip, "点击穿上")
    assert "点击穿上" in joined.note
