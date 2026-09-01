"""NPC 商店：买卖结算（钱不够 / 包满 / 卖价取整）。"""
from __future__ import annotations

from game import settings
from game.systems.inventory import Inventory, Item
from game.systems.shop import buy, sell, sell_price, shops_of, item_price


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
    """王年海（行商）可开药水/武器/卷轴三家店。"""
    assert shops_of("1012119") == ["potions", "weapons", "scrolls"]
    assert shops_of("1012110") == []


def test_item_price_fallback_for_scrolls():
    """自制卷轴无 WZ price → 回退兜底表。"""
    assert item_price("02340000", assets=None) == settings.FALLBACK_PRICES["02340000"]
