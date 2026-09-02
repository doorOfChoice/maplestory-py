"""NPC 商店：货架配置与买卖结算（纯函数，可单测）。

· SHOPS：商店 id → 货架物品 id 列表（8 位补零）；SHOP_NPCS：NPC → 可开的商店。
· 价格：优先 WZ info.price（assets.item_price），缺省回退 settings.FALLBACK_PRICES。
· buy/sell 为纯函数：buy 扣钱入包（钱不够 / 包满失败），sell 按 SELL_RATE 出售。
· Lua 脚本可在 content/npc/<npc_id>.lua 中导出 shops() 注册商店，
  运行时通过 register_lua_shop() 合并进 SHOPS / SHOP_NPCS。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from game import settings
from game.systems.inventory import Inventory, Item, item_kind

# ── 货架配置（商店 id → 物品 id 列表，id 为补零 8 位）────────────────
SHOPS: dict = {
    "potions": ["02000000", "02000003", "02000001", "02000002"],  # 红/蓝/橘/白药水
    "weapons": ["01452000", "01452002", "01302000"],              # 战斗弓/长弓/剑
    "scrolls": ["02340000", "02340002", "02340001"],              # 自制强化卷轴
}
SHOP_NAMES: dict = {"potions": "药水", "weapons": "武器", "scrolls": "卷轴"}

# NPC → 可开的商店列表（弓箭手村行商 王年海）
SHOP_NPCS: dict = {"1012119": ["potions", "weapons", "scrolls"]}
# 仓库 NPC（小安：帮你看着行李）
STORAGE_NPC = "1012110"

# Lua 脚本动态注册的商店数据（npc_id → 货架物品 id 列表）
_LUA_SHOPS: dict = {}


def register_lua_shop(npc_id: str, shop_ids: List[str]) -> None:
    """注册 Lua 脚本为 NPC 定义的商店列表。"""
    _LUA_SHOPS[str(npc_id)] = list(shop_ids)


def shops_of(npc_id: str) -> List[str]:
    """该 NPC 可开的商店列表。Lua 注册优先于硬编码配置。"""
    if str(npc_id) in _LUA_SHOPS:
        return list(_LUA_SHOPS[str(npc_id)])
    return list(SHOP_NPCS.get(npc_id) or [])


def item_price(item_id: str, assets=None) -> Optional[int]:
    """物品买价：优先 WZ price 字段；缺省回退兜底表（卷轴等自制物品）。"""
    if assets is not None:
        p = assets.item_price(item_id)
        if p is not None:
            return p
    return settings.FALLBACK_PRICES.get(item_id)


def buy(shop_id: str, item_id: str, meso: int, inventory: Inventory,
        price: Optional[int] = None, count: int = 1,
        make_fn: Optional[Callable] = None) -> Tuple[bool, int]:
    """购买 count 个物品：扣钱入包。返回 (是否成功, 剩余金币)。

    钱不够 / 背包满 / 该店不卖此物品时失败且金币不变；make_fn 缺省时
    构建无资产的最小 Item（测试用）。
    """
    if shop_id in SHOPS and item_id not in SHOPS[shop_id]:
        return False, meso
    if price is None:
        price = item_price(item_id) or 0
    cost = price * count
    if meso < cost:
        return False, meso
    item = (make_fn(item_id, count) if make_fn is not None
            else Item(id=item_id, count=count, kind=item_kind(item_id)))
    if not inventory.add(item):
        return False, meso
    return True, meso - cost


def sell_price(price: int) -> int:
    """单件出售价 = price × SELL_RATE 向下取整。"""
    return int(price * settings.SELL_RATE)


def sell(item: Item, meso: int, price: int) -> int:
    """出售整件/整堆：每单位回 SELL_RATE×price（向下取整），累加进金币。"""
    return meso + int(price * settings.SELL_RATE) * max(1, item.count)