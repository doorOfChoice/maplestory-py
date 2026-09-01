"""背包取出：整堆消耗 / 装备散件 / 已穿装备可被移除（扔出用）。"""

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
