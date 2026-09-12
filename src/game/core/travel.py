"""地图通行：传送门类型分类与目标地图校验（数据驱动）。

Map.wz 每个 portal 自带 tm（目标地图）/ tn（落点门名），地图连通关系
完全由 WZ 数据决定，取代旧的 TRAVEL_MAPS 白名单。
触发方式与原版对齐：
  · type 2      —— 站在门上按 ↑（pv 门）
  · type 10/11  —— 隐藏门：不绘制，但仍需按 ↑ 进入
  · type 1      —— 脚本门：有 tm 时降级为按 ↑（无脚本解释器）
  · type 3      —— 碰撞门：走进重叠即触发（无需按 ↑，如赫内西斯怪物之森告示牌）
  · type 7/8/9/11 —— 脚本门：WZ 只给 script 名、无 tm；已登记脚本（见
    register_portal_script）时按 ↑ 进入，否则跳过
  · type 4/5（pg/tp 命令门）多为事件噱头或自传，不开放
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple


NO_TARGET = 999999999        # WZ 无目标传送门的 tm 哨兵值
PORTAL_UP = 2                # pv 普通门：按 ↑ 传送（画 pv 动画）
PORTAL_HIDDEN = (10, 11)     # ph/psh 隐藏门：按 ↑ 传送（原版不绘制）
PORTAL_SCRIPT = (1,)         # pi 脚本门：有 tm 时降级为按 ↑（无脚本解释器）
PORTAL_COLLISION = (3,)      # pc 碰撞门：走进重叠即触发
PORTAL_SCRIPT_GATE = (7, 8, 9, 11)   # ps/脚本门：靠 script 名决定去向
TOWN_PORTAL = 6              # tp 城镇传送点：回程卷轴落点
# pt 4/5（pg/tp 命令门）多为事件噱头或自传，不开放

# script 名 → (目标地图 id, 落点门名或 None=sp)：启动期由 features 登记（见
# register_portal_script）。WZ 脚本门本身不带 tm，去向写死在登记表里。
_SCRIPT_PORTALS: Dict[str, Tuple[str, Optional[str]]] = {}


def portal_target(portal: Dict) -> Optional[str]:
    """目标地图 id（字符串）；无 tm 或为哨兵值时返回 None。

    无 tm 的脚本门若其 script 已登记，回传登记的目标图。
    """
    try:
        tm = int(portal.get("targetMap"))
    except (TypeError, ValueError):
        tm = 0
    if tm > 0 and tm != NO_TARGET:
        return str(tm)
    entry = _SCRIPT_PORTALS.get(str(portal.get("script") or ""))
    return entry[0] if entry is not None else None


def portal_trigger(portal: Dict) -> Optional[str]:
    """触发方式：'up' 按↑ / 'collision' 走进即触发 / None 不可通行。

    隐藏门与普通门一样需按↑；碰撞门无需按键；已登记脚本门按↑。
    """
    ptype = portal.get("type")
    if ptype == PORTAL_UP or ptype in PORTAL_HIDDEN:
        return "up"
    if ptype in PORTAL_COLLISION:
        return "collision"
    if ptype in PORTAL_SCRIPT and portal.get("name") != "sp":
        return "up"
    if ptype in PORTAL_SCRIPT_GATE and portal.get("script") in _SCRIPT_PORTALS:
        return "up"
    return None


def portal_hidden(portal: Dict) -> bool:
    """是否隐藏门：10/11 与原版脚本门不可见，但需按↑进入。"""
    if portal.get("type") in PORTAL_HIDDEN:
        return True
    return portal.get("type") in PORTAL_SCRIPT_GATE \
        and portal.get("script") in _SCRIPT_PORTALS


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
        # 脚本门登记的落点门名覆盖 WZ 里空着的 tn（普通门不受影响）
        entry = _SCRIPT_PORTALS.get(str(p.get("script") or ""))
        if entry is not None and entry[1]:
            q["targetName"] = entry[1]
        result.append(q)
    return result


# ── 脚本门登记（script 名 → 目标图）─────────────────────────────────

def register_portal_script(script: str, target_map: str,
                           target_name: Optional[str] = None) -> None:
    """登记脚本门的去向（启动期由 features 批量调用）。"""
    _SCRIPT_PORTALS[str(script)] = (str(target_map), target_name)


def register_portal_scripts(mapping: Dict[str, Tuple[str, Optional[str]]]) -> None:
    """批量登记脚本门：{script: (目标地图, 落点门名或 None)}。"""
    for script, (target_map, target_name) in mapping.items():
        register_portal_script(script, target_map, target_name)


def clear_portal_scripts() -> None:
    """清空脚本门登记表（测试隔离用）。"""
    _SCRIPT_PORTALS.clear()


# ── 回程卷轴目标 ────────────────────────────────────────────────────

def scroll_target(move_to: int, return_map) -> Optional[str]:
    """回程卷轴落点：moveTo 为哨兵时取当前地图 returnMap；无落点返回 None。"""
    if move_to == NO_TARGET:
        mid = str(int(return_map)) if return_map else None
        return None if mid == str(NO_TARGET) else mid
    return str(move_to)


def town_portal_position(portals: List[Dict]) -> Optional[Tuple[float, float]]:
    """城镇传送点（pt=6）坐标，回程卷轴落点；无则该点返回 None。"""
    for p in portals:
        if p.get("type") == TOWN_PORTAL:
            return float(p["x"]), float(p["y"])
    return None


# ── NPC 传送目的地（由 content/npc/*.lua 的 entries() 注册）──────────

# npc_id → [(目的地名, 地图 id, 票价), ...]；出租车等传送 NPC 的唯一事实来源在 Lua
_NPC_TELEPORTS: Dict[str, List[Tuple[str, str, int]]] = {}


def register_teleports(npc_id: str,
                       dests: List[Tuple[str, str, int]]) -> None:
    """登记某 NPC 的传送目的地（启动期由 lua_quests 调用）。"""
    _NPC_TELEPORTS[str(npc_id)] = list(dests)


def teleports_of(npc_id: str,
                 current_map: Optional[str] = None,
                 ) -> List[Tuple[str, str, int]]:
    """该 NPC 的目的地 (名字, 地图 id, 票价)；玩家已在某图时剔除该图。"""
    return [(name, mid, fare) for name, mid, fare
            in _NPC_TELEPORTS.get(str(npc_id), []) if mid != current_map]


def pay_fare(meso: int, fare: int) -> Optional[int]:
    """支付票价：余额足够回传扣费后的余额，不足回 None（调用方据此拒绝传送）。"""
    if fare <= 0:
        return meso
    return meso - fare if meso >= fare else None


def clear_teleports() -> None:
    """清空注册表（测试隔离用）。"""
    _NPC_TELEPORTS.clear()
