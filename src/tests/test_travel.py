"""地图通行纯函数：传送门目标解析、触发方式分类、可用性过滤（合成数据，不依赖 WZ）。"""
from __future__ import annotations

from game.core.travel import (NO_TARGET, pay_fare, portal_hidden, portal_target,
                              portal_trigger, register_portal_script, scroll_target,
                              town_portal_position, usable_portals)
from game.core import travel


def portal(ptype, tm=999999999, name="p"):
    return {"type": ptype, "targetMap": tm, "name": name, "x": 0, "y": 0}


def test_portal_target_reads_valid_tm():
    """有效 tm 回传字符串地图 id。"""
    assert portal_target(portal(2, tm=100000000)) == "100000000"


def test_portal_target_rejects_sentinel_and_missing():
    """无目标哨兵值 / 缺失 / 非数字都视为不可达。"""
    assert portal_target(portal(2, tm=999999999)) is None
    assert portal_target(portal(2, tm=None)) is None
    assert portal_target({"type": 2}) is None


def test_portal_trigger_by_type():
    """type 2 / 隐藏门 10/11 按↑；脚本门 1 有 tm 降级为按↑；
    碰撞门 3 走进即触发（collision）；sp 出生点不可用。"""
    assert portal_trigger(portal(2)) == "up"
    assert portal_trigger(portal(10)) == "up"
    assert portal_trigger(portal(11)) == "up"
    assert portal_trigger(portal(1, tm=100000000)) == "up"
    assert portal_trigger(portal(3, tm=100000000)) == "collision"
    assert portal_trigger(portal(0, name="sp")) is None


def test_portal_hidden_flag():
    """10/11 标记 hidden=True，普通门 / 脚本门为 False。"""
    assert portal_hidden(portal(10)) is True
    assert portal_hidden(portal(11)) is True
    assert portal_hidden(portal(2)) is False
    assert portal_hidden(portal(1)) is False


def test_usable_portals_filters_unreachable_target():
    """目标地图不存在于 Map.wz 的门被过滤掉。"""
    known = {"100000000"}
    portals = [
        portal(2, tm=100000000, name="up_ok"),
        portal(2, tm=999999999, name="no_target"),
        portal(2, tm=123456789, name="unknown_map"),
    ]
    result = usable_portals(portals, lambda mid: mid in known)
    assert [p["name"] for p in result] == ["up_ok"]
    assert result[0]["trigger"] == "up"
    assert result[0]["target_id"] == "100000000"


def test_usable_portals_keeps_contact_and_script_gates():
    """隐藏门（10）与有 tm 的脚本门（1）都保留：trigger 均为 up，隐藏门带 hidden 标记。"""
    portals = [portal(10, tm=100000000, name="hidden"),
               portal(1, tm=100000000, name="script")]
    result = usable_portals(portals, lambda mid: True)
    by_name = {p["name"]: p for p in result}
    assert by_name["hidden"]["trigger"] == "up"
    assert by_name["hidden"]["hidden"] is True
    assert by_name["script"]["trigger"] == "up"
    assert by_name["script"]["hidden"] is False


def test_same_map_flag_marks_self_target():
    """目标地图 == 当前地图时 same_map=True，否则为 False（同图瞬移门）。"""
    portals = [portal(2, tm=100000000, name="loop"),
               portal(2, tm=100000001, name="out")]
    result = usable_portals(portals, lambda mid: True, current_map="100000000")
    by_name = {p["name"]: p for p in result}
    assert by_name["loop"]["same_map"] is True
    assert by_name["out"]["same_map"] is False


def test_usable_portals_includes_collision_walk_in():
    """碰撞门（type 3）目标存在时保留，trigger=collision 且不标记 hidden（不绘制）。"""
    portals = [portal(3, tm=105040300, name="goSleepy0")]
    result = usable_portals(portals, lambda mid: mid == "105040300")
    assert [p["name"] for p in result] == ["goSleepy0"]
    assert result[0]["trigger"] == "collision"
    assert result[0]["hidden"] is False
    assert result[0]["target_id"] == "105040300"


# ── 脚本门：登记「script 名 → 目标图」后按↑进入 ─────────────────────

def script_portal(script, ptype=7, name="jobin00"):
    return {"type": ptype, "targetMap": NO_TARGET, "name": name, "script": script,
            "x": 0, "y": 0}


def test_unregistered_script_portal_is_skipped():
    """未登记的脚本门（无 tm）不可达，也不可触发。"""
    travel.clear_portal_scripts()
    p = script_portal("enterMagiclibrar")
    assert portal_target(p) is None
    assert portal_trigger(p) is None
    assert usable_portals([p], lambda mid: True) == []


def test_registered_script_portal_becomes_walk_in():
    """登记脚本名 → 目标图后：解析出目标、按↑触发、不绘制（hidden）。"""
    travel.clear_portal_scripts()
    register_portal_script("enterMagiclibrar", "101000003")
    p = script_portal("enterMagiclibrar")
    assert portal_target(p) == "101000003"
    assert portal_trigger(p) == "up"
    assert portal_hidden(p) is True
    result = usable_portals([p], lambda mid: mid == "101000003")
    assert len(result) == 1
    assert result[0]["trigger"] == "up"
    assert result[0]["hidden"] is True
    assert result[0]["target_id"] == "101000003"
    travel.clear_portal_scripts()


def test_scroll_target_resolves_sentinel_to_return_map():
    """回程卷轴 moveTo=999999999 → 当前图 returnMap；显式目标原样字符串化。"""
    assert scroll_target(NO_TARGET, 100000000) == "100000000"
    assert scroll_target(104000000, 100000000) == "104000000"


def test_scroll_target_without_return_map_is_none():
    assert scroll_target(NO_TARGET, 0) is None
    assert scroll_target(NO_TARGET, None) is None


# ── 回程卷轴落点：城镇传送点 pt=6 ─────────────────────────────────────

def test_town_portal_position_returns_type6_coords():
    """城镇传送点（pt=6）回传 (x, y)；多个时取第一个。"""
    portals = [portal(0, name="sp"), portal(6, name="tp"),
               portal(6, name="tp2")]
    assert town_portal_position(portals) == (0.0, 0.0)


def test_town_portal_position_none_without_type6():
    """无 pt=6 城镇传送点时回 None（调用方回退出生门）。"""
    assert town_portal_position([portal(0, name="sp"), portal(2, name="pv")]) is None


# ── 出租车票价 ──────────────────────────────────────────────────────

def test_pay_fare_deducts_when_affordable():
    """余额足够：回传扣费后的余额。"""
    assert pay_fare(1500, 1000) == 500


def test_pay_fare_zero_is_free():
    """票价 0 恒放行，余额不变。"""
    assert pay_fare(0, 0) == 0


def test_pay_fare_rejects_when_short():
    """余额不足（哪怕差 1）回 None，表示拒绝且不应扣费。"""
    assert pay_fare(999, 1000) is None
    assert pay_fare(0, 1) is None
