"""NPC 商店：货架配置与买卖结算（纯函数，可单测）。

商店数据完全来自脚本：content/npc/<npc_id>.lua 导出 shops()，经
register_lua_shop() 把每个商店的货架明细（物品 id + 买价）与显示名注册进来。
这里不再硬编码任何货架/价格/名称；无脚本注册的 NPC 没有商店。

· SHOPS       商店 id → 货架物品 id 列表（8 位补零）
· SHOP_NAMES  商店 id → 显示名（脚本缺省时回退 shop_id）
· SHOP_PRICING 商店 id → 物品 id → 脚本买价（缺省即走 WZ / 兜底表）
· 买价优先级：脚本价 > WZ info.price（assets.item_price）> settings.FALLBACK_PRICES
  （「其他」类再走 ETC 分档表，见 item_price）
· buy/sell 为纯函数：buy 扣钱入包（钱不够 / 包满失败），sell 按 SELL_RATE 出售。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from game import settings
from game.systems.inventory import Inventory, Item, item_kind

# 商店 id → 货架物品 id 列表（全部由 Lua 脚本注册，无硬编码）
SHOPS: dict = {}
# 商店 id → 显示名（脚本缺省时回退 shop_id）
SHOP_NAMES: dict = {}
# 商店 id → 物品 id → 脚本买价（缺省即走 WZ / 兜底表）
SHOP_PRICING: dict = {}

# NPC → 可开的商店 id 列表（Lua 脚本注册）
_LUA_SHOPS: dict = {}

# 仓库 NPC（小安：帮你看着行李）
STORAGE_NPC = "1012110"


def register_lua_shop(npc_id: str, shop_ids: List[str]) -> None:
    """记录 NPC 可开的商店列表（顺序即页签顺序）。"""
    _LUA_SHOPS[str(npc_id)] = list(shop_ids)


def register_shop_profile(shop_id: str, name: Optional[str],
                          items: List[Tuple[str, int]]) -> None:
    """注册单个商店的货架明细与买价。

    items 为 [(item_id, price), ...]，price 可能为 0（表示改用 WZ/兜底价）；
    缺省名回退 shop_id。
    """
    SHOPS[shop_id] = [iid for iid, _ in items]
    SHOP_NAMES[shop_id] = (name or shop_id)
    SHOP_PRICING[shop_id] = dict(items)


def shops_of(npc_id: str) -> List[str]:
    """该 NPC 可开的商店列表。"""
    return list(_LUA_SHOPS.get(str(npc_id)) or [])


def shop_name(shop_id: str) -> str:
    """商店显示名，缺省回退 shop_id。"""
    return SHOP_NAMES.get(shop_id, shop_id)


def shop_price(shop_id: str, item_id: str) -> Optional[int]:
    """脚本为该店该物品定的买价；无脚本价返回 None。"""
    return SHOP_PRICING.get(shop_id, {}).get(item_id)


def item_price(item_id: str, assets=None) -> Optional[int]:
    """物品基础买价：优先 WZ price 字段；缺省回退兜底表（卷轴等自制物品）。

    「其他」类（04xxxxxx）WZ 无 price 字段，走 settings 分档表：
    单件覆盖 ETC_PRICES > 段分档 ETC_PRICE_TIERS > ETC_DEFAULT_PRICE。
    """
    if assets is not None:
        p = assets.item_price(item_id)
        if p is not None:
            return p
    p = settings.FALLBACK_PRICES.get(item_id)
    if p is not None:
        return p
    iid = str(item_id).zfill(8)
    if iid.startswith("04"):
        return (settings.ETC_PRICES.get(iid)
                or settings.ETC_PRICE_TIERS.get(iid[:5])
                or settings.ETC_DEFAULT_PRICE)
    return None


def buy_price(shop_id: str, item_id: str, assets=None) -> Optional[int]:
    """该店该物品的最终买价：脚本价 > WZ 价 > 兜底表。"""
    p = shop_price(shop_id, item_id)
    if p is not None:
        return p
    return item_price(item_id, assets)


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
        price = buy_price(shop_id, item_id) or 0
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
