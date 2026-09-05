"""右下角战斗明细模型：击杀经验/拾取金币条目、一次一条、限时淡出。"""

from __future__ import annotations

import pytest

from game.core.combat_log import CombatLog


def make_log():
    """注入假时钟的 CombatLog：手动拨表推进时间。"""
    t = {"now": 0.0}
    log = CombatLog(now=lambda: t["now"])
    return log, t


def test_add_exp_creates_entry_with_amount_and_name():
    """击杀加经验：出一条 exp 条目，携带怪名与经验值。"""
    log, _ = make_log()
    log.add_exp("100101", "蓝蜗牛", 3)
    assert len(log.entries) == 1
    e = log.entries[0]
    assert (e.kind, e.name, e.amount) == ("exp", "蓝蜗牛", 3)


def test_each_event_gets_its_own_entry_no_merging():
    """同怪连杀、连捡金币/物品：一次事件一条，互不合并。"""
    log, _ = make_log()
    log.add_exp("100101", "蓝蜗牛", 3)
    log.add_exp("100101", "蓝蜗牛", 3)
    log.add_meso(10)
    log.add_meso(25)
    log.add_item("4000000", "蓝螺壳", 1)
    log.add_item("4000000", "蓝螺壳", 2)
    assert [(e.kind, e.amount) for e in log.entries] == \
        [("exp", 3), ("exp", 3), ("meso", 10), ("meso", 25),
         ("item", 1), ("item", 2)]


def test_entries_expire_after_ttl():
    """条目存活满 TTL 后由 update 清除。"""
    log, t = make_log()
    log.add_exp("100101", "蓝蜗牛", 3)
    for _ in range(10):
        t["now"] += 0.5
        log.update()
    assert log.entries == []


def test_fresh_entry_is_full_alpha_and_expiring_fades():
    """淡出窗口为存活期最后 fade 秒：窗口前全亮，窗口内线性降到 0。"""
    log, t = make_log()
    log.add_meso(10)
    e = log.entries[0]
    assert e.alpha == 1.0
    t["now"] += log.ttl - log.fade + 0.2   # 淡出窗口内 0.2s
    assert e.alpha == pytest.approx(1 - 0.2 / log.fade)
    t["now"] += log.fade - 0.2             # 淡出终点
    assert e.alpha == 0.0


def test_overflow_drops_oldest_entry():
    """条目数超上限时挤掉最旧的，新条目始终可见。"""
    log, _ = make_log()
    n = log.max_entries + 3
    for i in range(n):
        log.add_item(f"40000{i:02d}", f"物品{i}", 1)
    assert len(log.entries) == log.max_entries
    assert log.entries[-1].name == f"物品{n - 1}"
