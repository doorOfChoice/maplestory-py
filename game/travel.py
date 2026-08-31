"""地图通行：传送门类型分类与目标地图校验（数据驱动）。

Map.wz 每个 portal 自带 tm（目标地图）/ tn（落点门名），地图连通关系
完全由 WZ 数据决定，取代旧的 TRAVEL_MAPS 白名单。
触发方式与原版对齐：
  · type 2      —— 站在门上按 ↑
  · type 6/7/9  —— 碰到即传送（隐藏门 / 碰撞门，不绘制）
  · 脚本门 0/1/4/5/10 —— 有 tm 时降级为按 ↑（无脚本解释器）
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

NO_TARGET = 999999999        # WZ 无目标传送门的 tm 哨兵值
PORTAL_UP = 2                # pv 普通门：按 ↑ 传送（画 pv 动画）
PORTAL_HIDDEN = (10, 11)     # ph/psh 隐藏门：碰到即传送（原版不绘制）
PORTAL_SCRIPT = (1,)         # pi 脚本门：有 tm 时降级为按 ↑（无脚本解释器）
# pt 3/4/5（pc/pg/tp 命令门）多为事件噱头或自传，不开放


def portal_target(portal: Dict) -> Optional[str]:
    """目标地图 id（字符串）；无 tm 或为哨兵值时返回 None。"""
    try:
        tm = int(portal.get("targetMap"))
    except (TypeError, ValueError):
        return None
    if tm <= 0 or tm == NO_TARGET:
        return None
    return str(tm)


def portal_trigger(portal: Dict) -> Optional[str]:
    """触发方式：'up' 按↑ / 'contact' 碰到即传送 / None 不可通行。"""
    ptype = portal.get("type")
    if ptype == PORTAL_UP:
        return "up"
    if ptype in PORTAL_HIDDEN:
        return "contact"
    if ptype in PORTAL_SCRIPT and portal.get("name") != "sp":
        return "up"
    return None


def usable_portals(portals: List[Dict],
                   has_map: Callable[[str], bool]) -> List[Dict]:
    """筛出可通行的传送门，附加 trigger / target_id 字段。

    has_map 用于校验目标地图真实存在于 Map.wz（含 info/link 重定向）。
    """
    result: List[Dict] = []
    for p in portals:
        trigger = portal_trigger(p)
        tm = portal_target(p)
        if trigger is None or tm is None or not has_map(tm):
            continue
        q = dict(p)
        q["trigger"] = trigger
        q["target_id"] = tm
        result.append(q)
    return result
