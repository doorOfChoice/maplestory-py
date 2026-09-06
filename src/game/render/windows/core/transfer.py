"""跨窗拖放取出：把「拖到商店卖出 / 拖到仓库存入」的来源解析收敛为单源。

DragPickup 的 source 描述物品原位（背包格 / 纸娃娃槽）；投递窗口经确认弹框
拿到最终数量后调用本函数取出实物。任何一步来源失效（物品被消耗/换位）都
返回 None，由调用方提示，绝不误扣他物。
"""

from __future__ import annotations

from typing import Optional

from game.systems.inventory import Item


def take_from_source(player, pk, qty: Optional[int]) -> Optional[Item]:
    """按 DragPickup 来源取出 qty 个（堆叠）/ 1 件（装备）；失效返回 None。"""
    inv = player.inventory
    item = pk.item
    if item is None:
        return None
    src = pk.source
    if getattr(item, "kind", "") in ("consume", "etc"):
        cur = inv.consumes.get(item.id) or inv.etcs.get(item.id)
        if cur is None:
            return None
        n = cur.count if qty is None else min(qty, cur.count)
        return inv.take_units(item.id, n)
    if src and src[0] == "cell" and src[1] == "equip":
        idx = src[2]
        if 0 <= idx < len(inv.equips) and inv.equips[idx] is item:
            return inv.pop_equip(idx)
        return None
    if src and src[0] == "slot":
        if inv.equipped.get(src[1]) is item:
            got = inv.pop_equipped(src[1])
            if got is not None:
                player.refresh_equips()
            return got
        return None
    return None
