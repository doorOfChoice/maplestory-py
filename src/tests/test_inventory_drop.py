"""背包取出：整堆消耗 / 按数量拆堆 / 装备散件 / 已穿装备可被移除（扔出 / 商店用）。"""

from game.systems.inventory import Inventory, Item


def test_take_stack_removes_entry():
    inv = Inventory()
    inv.add(Item(id="2000000", name="红药", count=12, kind="consume"))
    got = inv.take_stack("2000000")
    assert got is not None and got.count == 12
    assert inv.consumes == {}
    assert inv.take_stack("2000000") is None


def test_take_stack_works_for_etc():
    inv = Inventory()
    inv.add(Item(id="4000000", name="木块", count=5, kind="etc"))
    got = inv.take_stack("4000000")
    assert got is not None and got.count == 5
    assert inv.etcs == {}


def test_take_units_splits_partial_stack():
    """按数量拆堆取出：取不满留余量，取满整堆删条目。"""
    inv = Inventory()
    inv.add(Item(id="2000000", name="红药", count=5, kind="consume"))
    got = inv.take_units("2000000", 2)
    assert got is not None and got.count == 2
    assert inv.consumes["2000000"].count == 3
    got = inv.take_units("2000000", 3)
    assert got is not None and got.count == 3
    assert "2000000" not in inv.consumes
    assert inv.take_units("2000000", 1) is None


def test_take_units_rejects_bad_input():
    """非法数量 / 不存在物品均返回 None，背包不动。"""
    inv = Inventory()
    inv.add(Item(id="4000000", name="木块", count=5, kind="etc"))
    assert inv.take_units("4000000", 0) is None
    assert inv.take_units("9999999", 2) is None
    assert inv.etcs["4000000"].count == 5


def test_pop_equip_removes_from_bag():
    inv = Inventory()
    e = Item(id="1040013", kind="equip", info={"islot": "SoSh"})
    inv.add(e)
    assert inv.pop_equip(0) is e
    assert inv.equips == []
    assert inv.pop_equip(0) is None


def test_pop_equipped_removes_from_slot():
    inv = Inventory()
    e = Item(id="1040013", kind="equip", info={"islot": "SoSh"})
    inv.equipped["shoes"] = e
    assert inv.pop_equipped("shoes") is e
    assert inv.equipped == {}
    assert inv.pop_equipped("shoes") is None
