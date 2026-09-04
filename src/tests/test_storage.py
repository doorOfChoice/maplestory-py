"""仓库：背包↔仓库双向存取与容量限制（复用 storage_add/storage_take）。"""
from __future__ import annotations

from game import settings
from game.systems.inventory import Inventory, Item


def test_bag_to_storage_and_back_roundtrip():
    """背包整堆 → 仓库 → 取出回背包，数量与内容不变。"""
    inv = Inventory()
    inv.add(Item(id="02000000", name="红水", count=5, kind="consume"))
    it = inv.take_stack("02000000")
    assert it is not None and it.count == 5
    assert inv.storage_add(it)
    assert len(inv.storage) == 1 and inv.storage[0].count == 5
    got = inv.storage_take(0)
    assert got is not None and got.count == 5
    assert inv.add(got)
    assert inv.consumes["02000000"].count == 5


def test_storage_merges_same_id_consume():
    """同 id 消耗品入仓自动合并堆叠。"""
    inv = Inventory()
    assert inv.storage_add(Item(id="02000000", count=2, kind="consume"))
    assert inv.storage_add(Item(id="02000000", count=3, kind="consume"))
    assert len(inv.storage) == 1 and inv.storage[0].count == 5


def test_storage_keeps_equips_as_separate_slots():
    """装备逐件占格，不入合并。"""
    inv = Inventory()
    inv.storage_add(Item(id="01452002", kind="equip"))
    inv.storage_add(Item(id="01040000", kind="equip"))
    assert len(inv.storage) == 2


def test_storage_capacity_rejects_overflow():
    """超过 STORAGE_CAP 时入仓失败。"""
    inv = Inventory()
    for i in range(settings.STORAGE_CAP):
        assert inv.storage_add(Item(id=f"{4000000 + i:07d}", kind="etc"))
    assert not inv.storage_add(Item(id="4003000", kind="etc"))
    assert len(inv.storage) == settings.STORAGE_CAP


def test_storage_take_out_of_range():
    """越界取出返回 None。"""
    inv = Inventory()
    assert inv.storage_take(0) is None
    assert inv.storage_take(-1) is None
    assert inv.storage_take(99) is None


def test_storage_equip_roundtrip_keeps_extra():
    """强化过的装备入仓再取出，extra/tuc 保真。"""
    inv = Inventory()
    w = Item(id="01452002", name="长弓", kind="equip", info={"islot": "WpSi", "tuc": 7})
    w.extra["incPAD"] = 4
    w.tuc = 3
    assert inv.storage_add(w)
    inv2 = Inventory.from_dict(inv.to_dict(), assets=None)
    got = inv2.storage_take(0)
    assert got.extra["incPAD"] == 4
    assert got.tuc == 3


def test_wheel_down_scrolls_bag_list_forward():
    """仓库背包列表超过一屏后，滚轮向下滚动首行索引递增（能看到更后面的物品）。"""
    from types import SimpleNamespace
    from game.render.windows.core.services import WindowServices
    from game.render.windows.storage import StorageWindow
    from tests.windows_harness import FakeAssets, FakeUI

    inv = Inventory()
    for i in range(40):
        inv.add(Item(id=f"40000{i:03d}", count=1, kind="etc"))
    p = SimpleNamespace(inventory=inv)

    win = StorageWindow(WindowServices(assets=FakeAssets(), ui=FakeUI(),
                                       player=lambda: p))
    win.open()
    assert win.handle_wheel((110, 110), 1)
    assert win._scroll == 1
    win.handle_wheel((110, 110), 1)
    assert win._scroll == 2
    win.handle_wheel((110, 110), -1)
    assert win._scroll == 1
