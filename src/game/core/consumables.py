"""消耗品使用结算：恢复量计算与门控判定（纯函数，编排见 Player）。

WZ Consume spec 只取本项目实现的键：hp/mp（固定恢复）、hpR/mpR（按上限
百分比恢复）、moveTo（回程卷轴目标地图，999999999 为「当前图 returnMap」
哨兵，由 warp 回调方解析）。其余键（buff time / morph / 弹药等）不可用。

warp 回调契约：Callable[[int], Optional[str]] —— 入参为 moveTo 原始值；
成功（已开始切图）返回 None，被拒返回简体中文原因。调用方只在回调
成功后才扣物品，避免吞卷轴不生效。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

WarpFn = Callable[[int], Optional[str]]


def spec_int(spec: Dict, key: str) -> int:
    try:
        return int(spec.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def is_healing(spec: Dict) -> bool:
    return any(spec_int(spec, k) for k in ("hp", "mp", "hpR", "mpR"))


def is_return_scroll(spec: Dict) -> bool:
    return spec_int(spec, "moveTo") > 0


def heal_amounts(spec: Dict, max_hp: int, max_mp: int) -> Tuple[int, int]:
    """本次应恢复的 hp/mp 量（固定值 + 上限百分比，向下取整）。"""
    hp = spec_int(spec, "hp") + max_hp * spec_int(spec, "hpR") // 100
    mp = spec_int(spec, "mp") + max_mp * spec_int(spec, "mpR") // 100
    return hp, mp


def heal_block_reason(spec: Dict, hp: int, max_hp: int,
                      mp: int, max_mp: int) -> Optional[str]:
    """治疗药门控：应恢复量在满值的 vital 上无效时给出原因。"""
    add_hp, add_mp = heal_amounts(spec, max_hp, max_mp)
    if (add_hp <= 0 or hp >= max_hp) and (add_mp <= 0 or mp >= max_mp):
        return "HP/MP 已满，无需使用"
    return None


def apply_heal(spec: Dict, player: Any) -> None:
    """治疗结算：按上限钳制。"""
    add_hp, add_mp = heal_amounts(spec, player.max_hp, player.max_mp)
    if add_hp:
        player.hp = min(player.max_hp, player.hp + add_hp)
    if add_mp:
        player.mp = min(player.max_mp, player.mp + add_mp)


def use(player: Any, item_id: str) -> Optional[str]:
    """使用消耗品的唯一方口（先验后扣）。

    成功返回 None，失败返回简体中文原因（可直接 flash）。鸭子类型契约：
    player 需提供 inventory(Inventory) 与 hp/max_hp/mp/max_mp，
    可选 on_warp(moveTo) → Optional[str]。
    """
    inv = player.inventory
    spec = inv.peek_consume(item_id)
    if spec is None:
        return "没有该物品"
    if is_return_scroll(spec):
        warp = getattr(player, "on_warp", None)
        if warp is None:
            return "当前无法使用回程卷轴"
        err = warp(spec_int(spec, "moveTo"))
        if err is not None:
            return err
        inv.use_consume(item_id)
        return None
    if not is_healing(spec):
        return "无法使用该物品"
    block = heal_block_reason(spec, player.hp, player.max_hp,
                              player.mp, player.max_mp)
    if block is not None:
        return block
    inv.use_consume(item_id)
    apply_heal(spec, player)
    return None
