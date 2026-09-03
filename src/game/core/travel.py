"""地图通行：传送门类型分类与目标地图校验（数据驱动）。

Map.wz 每个 portal 自带 tm（目标地图）/ tn（落点门名），地图连通关系
完全由 WZ 数据决定，取代旧的 TRAVEL_MAPS 白名单。
触发方式与原版对齐：
  · type 2      —— 站在门上按 ↑（pv 门）
  · type 10/11  —— 隐藏门：不绘制，但仍需按 ↑ 进入
  · type 1      —— 脚本门：有 tm 时降级为按 ↑（无脚本解释器）
  · type 3/4/5（pc/pg/tp 命令门）多为事件噱头或自传，不开放
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple


NO_TARGET = 999999999        # WZ 无目标传送门的 tm 哨兵值
PORTAL_UP = 2                # pv 普通门：按 ↑ 传送（画 pv 动画）
PORTAL_HIDDEN = (10, 11)     # ph/psh 隐藏门：按 ↑ 传送（原版不绘制）
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
    """触发方式：'up' 按↑ / None 不可通行。隐藏门与普通门一样需按↑。"""
    ptype = portal.get("type")
    if ptype == PORTAL_UP or ptype in PORTAL_HIDDEN:
        return "up"
    if ptype in PORTAL_SCRIPT and portal.get("name") != "sp":
        return "up"
    return None


def portal_hidden(portal: Dict) -> bool:
    """是否隐藏门（ph/psh）：不可见，但需按↑进入。"""
    return portal.get("type") in PORTAL_HIDDEN


def usable_portals(portals: List[Dict],
                   has_map: Callable[[str], bool],
                   current_map: Optional[str] = None) -> List[Dict]:
    """筛出可通行的传送门，附加 trigger / target_id / same_map 字段。

    has_map 用于校验目标地图真实存在于 Map.wz（含 info/link 重定向）。
    current_map 为当前地图 id：目标同图时置 same_map=True，
    供上层做无加载的原地瞬移（原版同图门用 psh 缩小动画）。
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
        q["hidden"] = portal_hidden(p)
        q["same_map"] = current_map is not None and tm == current_map
        result.append(q)
    return result


# ── NPC 传送目的地（由 content/npc/*.lua 的 entries() 注册）──────────

# npc_id → [(目的地名, 地图 id), ...]；出租车等传送 NPC 的唯一事实来源在 Lua
_NPC_TELEPORTS: Dict[str, List[Tuple[str, str]]] = {}


def register_teleports(npc_id: str, dests: List[Tuple[str, str]]) -> None:
    """登记某 NPC 的传送目的地（启动期由 lua_quests 调用）。"""
    _NPC_TELEPORTS[str(npc_id)] = list(dests)


def teleports_of(npc_id: str,
                 current_map: Optional[str] = None) -> List[Tuple[str, str]]:
    """该 NPC 的目的地 (名字, 地图 id)；玩家已在某图时剔除该图。"""
    return [(name, mid) for name, mid in _NPC_TELEPORTS.get(str(npc_id), [])
            if mid != current_map]


def clear_teleports() -> None:
    """清空注册表（测试隔离用）。"""
    _NPC_TELEPORTS.clear()
