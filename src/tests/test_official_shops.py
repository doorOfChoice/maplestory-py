"""官方 v113 商店货架导入：content/npc/*.lua 经正式流程注册为可开商店。

透过公开 seam 测试：load_lua_quest_defs（真实 content/npc 目录）→ shops_of /
SHOPS / buy_price / buy，不依赖 WZ。
"""
from __future__ import annotations

import pytest

from game.systems.lua_quests import load_lua_quest_defs
from game.systems.inventory import Inventory
from game.systems.shop import (
    SHOPS, buy, buy_price, shop_name, shops_of,
)

pytest.importorskip("lupa")

load_lua_quest_defs()


def test_official_shop_npcs_have_registered_shelves():
    """经典商人（克尔/科尔）启动扫描后能开出非空货架。"""
    for npc_id in ("1011000", "1012004"):
        ids = shops_of(npc_id)
        assert ids, npc_id
        assert all(SHOPS.get(sid) for sid in ids)
        assert shop_name(ids[0])


def test_official_shelf_items_are_padded_and_priced():
    """货架物品 id 一律 8 位补零；脚本价存在且为正。"""
    for npc_id in ("1011000", "1012004"):
        for sid in shops_of(npc_id):
            for item_id in SHOPS[sid]:
                assert len(item_id) == 8 and item_id.isdigit()
                assert buy_price(sid, item_id, assets=None) > 0


def test_buy_from_official_shelf_deducts_script_price():
    """从官方货架购买：按脚本价扣钱入包。"""
    sid = shops_of("1012004")[0]
    item_id = SHOPS[sid][0]
    price = buy_price(sid, item_id, assets=None)
    inv = Inventory()
    # buy 仅在物品成功入包时才返回 True
    ok, meso = buy(sid, item_id, price + 100, inv, price=price)
    assert ok and meso == 100
