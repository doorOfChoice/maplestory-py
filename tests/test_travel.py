"""地图通行纯函数：传送门目标解析、触发方式分类、可用性过滤（合成数据，不依赖 WZ）。"""
from __future__ import annotations

from game.travel import portal_target, portal_trigger, usable_portals


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
    """type 2 按↑；10/11 碰撞即传；脚本门 1 有 tm 降级为按↑；sp 出生点不可用。"""
    assert portal_trigger(portal(2)) == "up"
    assert portal_trigger(portal(10)) == "contact"
    assert portal_trigger(portal(11)) == "contact"
    assert portal_trigger(portal(1, tm=100000000)) == "up"
    assert portal_trigger(portal(3, tm=100000000)) is None   # 命令门不开放
    assert portal_trigger(portal(0, name="sp")) is None


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
    """隐藏门（10）与有 tm 的脚本门（1）都保留，并带正确 trigger。"""
    portals = [portal(10, tm=100000000, name="hidden"),
               portal(1, tm=100000000, name="script")]
    result = usable_portals(portals, lambda mid: True)
    triggers = {p["name"]: p["trigger"] for p in result}
    assert triggers == {"hidden": "contact", "script": "up"}
