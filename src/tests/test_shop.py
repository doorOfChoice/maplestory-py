"""NPC 商店：买卖结算（钱不够 / 包满 / 卖价取整）+ Lua 动态注册商店。"""
from __future__ import annotations

from game import settings
from game.systems.inventory import Inventory, Item
from game.systems.shop import (
    SHOPS, SHOP_PRICING, STORAGE_NPC,
    buy, sell, sell_price, shops_of, shop_name, buy_price, item_price,
    register_lua_shop, register_shop_profile,
)
from game.systems import dialogues

# ── 商店数据由 Lua 注册，测试前先登记一份货架（按正式流程 register_shop_profile）──
def _setup_merchant():
    register_lua_shop("1012119", ["potions", "weapons", "scrolls"])
    register_shop_profile("potions", "药水", [
        ("02000000", 25), ("02000003", 300), ("02000001", 30), ("02000002", 20)])
    register_shop_profile("weapons", "武器", [
        ("01452000", 10000), ("01452002", 8000)])
    register_shop_profile("scrolls", "卷轴", [
        ("02340000", 150), ("02340002", 200), ("02340001", 100)])


_setup_merchant()


def test_buy_deducts_meso_and_adds_item():
    """购买成功：扣钱、物品入包。"""
    inv = Inventory()
    ok, meso = buy("potions", "02000000", 100, inv, price=25)
    assert ok and meso == 75
    assert inv.consumes["02000000"].count == 1


def test_buy_insufficient_meso_fails_without_change():
    """钱不够：不成交、金币不变、背包不变。"""
    inv = Inventory()
    ok, meso = buy("potions", "02000000", 10, inv, price=25)
    assert not ok and meso == 10
    assert inv.consumes == {}


def test_buy_bag_full_fails():
    """背包装备栏满：购买装备失败且金币不变。"""
    inv = Inventory()
    inv.equips = [Item(id="01040000", kind="equip")
                  for _ in range(settings.INVENTORY_EQUIP_CAP)]
    ok, meso = buy("weapons", "01452000", 9999, inv, price=1000)
    assert not ok and meso == 9999
    assert len(inv.equips) == settings.INVENTORY_EQUIP_CAP


def test_buy_shop_not_stock_fails():
    """货架没有的物品不允许购买。"""
    inv = Inventory()
    ok, meso = buy("potions", "01452000", 9999, inv, price=100)
    assert not ok and meso == 9999


def test_sell_price_floors_half():
    """出售价 = 买价 × SELL_RATE 向下取整（25→12、100→50）。"""
    assert sell_price(25) == 12
    assert sell_price(100) == 50
    assert sell_price(1500) == 750


def test_sell_adds_meso_for_stack():
    """整堆出售：每单位按取整价计入金币。"""
    it = Item(id="02000000", name="红水", count=5, kind="consume")
    assert sell(it, 100, 25) == 100 + 12 * 5


def test_sell_single_equip():
    """单件装备出售：按单件取整价计。"""
    it = Item(id="01452002", kind="equip", count=1)
    assert sell(it, 0, 1500) == 750


def test_shops_of_merchant_npc():
    """注册了商店的行商可开三家店；未注册 NPC 无商店。"""
    assert shops_of("1012119") == ["potions", "weapons", "scrolls"]
    assert shops_of("1012110") == []


def test_shop_name_defaults_to_id():
    """注册时未给名 → 回退 shop_id。"""
    register_shop_profile("unnamed_shop", None, [("02000000", 10)])
    assert shop_name("unnamed_shop") == "unnamed_shop"


def test_buy_price_script_overrides_fallback():
    """脚本买价优先：potions 里 02000003 脚本价 300（WZ 为 100）。"""
    assert buy_price("potions", "02000003") == 300


def test_buy_price_falls_back_to_wz_when_no_script_price():
    """未定脚本价 → 回退 WZ/兜底；两处都有缺省则回 None。"""
    register_shop_profile("scrolls", "卷轴", [("02340000", 150)])
    assert buy_price("scrolls", "02340000") == 150
    # 脚本未定价、且无 WZ/兜底表的物品 → 回 None
    assert buy_price("scrolls", "02000004") is None


def test_item_price_fallback_for_scrolls():
    """自制卷轴无 WZ price → 回退兜底表。"""
    assert item_price("02340000", assets=None) == settings.FALLBACK_PRICES["02340000"]


def test_register_lua_shop_for_unknown_npc():
    """未注册的 NPC 返回空列表。"""
    assert shops_of("9999998") == []


def test_register_lua_dialogue():
    """dialogues.register_lua_dialogue 注册的台词优先于硬编码 DIALOGUES。"""
    dialogues.register_lua_dialogue("9999999", [["Lua 台词 1", "Lua 台词 2"]])
    got = dialogues.get_dialog("9999999")
    assert got == ["Lua 台词 1", "Lua 台词 2"]
    # 清理
    dialogues.DIALOGUES.pop("9999999", None)


def test_get_dialogue_fallback_to_generic():
    """未收录 NPC 回退通用池。"""
    got = dialogues.get_dialog("9999998", "路人")
    assert got is not None
    assert len(got) > 0
