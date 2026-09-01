"""存檔系統：序列化/反序列化雙向一致性 + 檔案 IO 測試。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from game.inventory import Inventory, Item
from game.quests import QuestLog, QuestDef
from game.save_manager import SaveManager


def test_inventory_to_from_dict_roundtrip():
    """Inventory → dict → Inventory，id/count 不變，kind 正確。"""
    inv = Inventory()
    inv.consumes["2000000"] = Item(id="2000000", name="紅水", count=12, kind="consume")
    inv.etcs["4000003"] = Item(id="4000003", name="木柴", count=5, kind="etc")
    inv.equips = [Item(id="01040000", name="弓手帽", kind="equip")]
    inv.equipped["weapon"] = Item(id="01302000", name="初心者之劍", kind="equip")
    inv.equipped["top"] = Item(id="01060000", name="弓手服", kind="equip")

    d = inv.to_dict()
    assert d["consumes"] == {"2000000": 12}
    assert d["etcs"] == {"4000003": 5}
    assert d["equips"] == ["01040000"]
    assert d["equipped"] == {"weapon": "01302000", "top": "01060000"}

    inv2 = Inventory.from_dict(d, assets=None)
    assert inv2.consumes["2000000"].count == 12
    assert inv2.consumes["2000000"].id == "2000000"
    assert inv2.etcs["4000003"].count == 5
    assert inv2.equips[0].id == "01040000"
    assert inv2.equipped["weapon"].id == "01302000"


def test_inventory_to_from_dict_empty():
    """空背包 roundtrip 不噴錯。"""
    inv = Inventory()
    d = inv.to_dict()
    inv2 = Inventory.from_dict(d, assets=None)
    assert len(inv2.consumes) == 0
    assert len(inv2.etcs) == 0
    assert len(inv2.equips) == 0
    assert len(inv2.equipped) == 0


def test_skillbook_to_from_dict_roundtrip():
    """SkillBook → dict → SkillBook，sp 與 levels 一致。"""
    from game.skills import SkillBook
    class FakeAssets:
        class FakeWz:
            class Root:
                images = {}
                subdirs = {}
            root = Root()
        def __init__(self):
            self.wz = {"Skill": self.FakeWz(), "String": self.FakeWz()}
    sb = SkillBook(FakeAssets(), 0)
    sb.sp = 10
    sb.levels["1001004"] = 3
    sb.levels["1001005"] = 1

    d = sb.to_dict()
    assert d["sp"] == 10
    assert d["levels"] == {"1001004": 3, "1001005": 1}

    sb2 = SkillBook(FakeAssets(), 0)
    sb2.from_dict(d)
    assert sb2.sp == 10
    assert sb2.levels["1001004"] == 3
    assert sb2.levels["1001005"] == 1


def test_questlog_to_from_dict_roundtrip():
    """QuestLog → dict → QuestLog，status/kills/accepted_order 一致。"""
    ql = QuestLog({})
    ql.status["2088"] = "accepted"
    ql.status["10037"] = "completed"
    ql.kills["2088"] = {2100100: 3}
    ql.accepted_order = ["2088"]

    d = ql.to_dict()
    assert d["status"]["2088"] == "accepted"
    assert d["kills"]["2088"]["2100100"] == 3
    assert d["accepted_order"] == ["2088"]

    ql2 = QuestLog({})
    ql2.from_dict(d)
    assert ql2.status["2088"] == "accepted"
    assert ql2.kills["2088"][2100100] == 3
    assert ql2.accepted_order == ["2088"]


def test_save_manager_write_read_roundtrip():
    """SaveManager.flush + load 檔案內容一致。"""
    data = {"version": 4, "player": {"level": 5, "hp": 80, "job": 0,
                                     "stats": {"str": 4, "dex": 4, "int": 4, "luk": 4},
                                     "ap": 0}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "save.json"
        sm = SaveManager(path)
        sm.flush(data)
        assert path.exists()
        loaded = sm.load()
        assert loaded == data


def test_save_manager_request_save_eventually_persists():
    """request_save 非同步提交後，後台線程最終寫入磁碟。"""
    data = {"version": 4, "player": {"level": 7, "hp": 60, "job": 0,
                                     "stats": {"str": 4, "dex": 4, "int": 4, "luk": 4},
                                     "ap": 0}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "save.json"
        sm = SaveManager(path)
        sm.request_save(data)
        sm.flush()
        assert sm.load() == data


def test_migrate_v2_adds_stats_by_job():
    """v2 旧档迁移：Lv12 弓箭手按职业权重把 (12-1)×5=55 AP 全进 DEX。"""
    v2 = {"version": 2, "player": {"level": 12, "exp": 0, "hp": 100,
                                   "max_hp": 120, "mp": 30, "max_mp": 40,
                                   "job": 3000}}
    migrated = SaveManager.migrate(v2)
    assert migrated["version"] == 4
    assert migrated["player"]["stats"]["dex"] == 4 + 55
    assert migrated["player"]["ap"] == 0


def test_migrate_v3_adds_storage():
    """v3 旧档迁移：inventory 补空 storage 字段。"""
    v3 = {"version": 3, "player": {"level": 5}, "inventory": {"consumes": {}}}
    migrated = SaveManager.migrate(v3)
    assert migrated["version"] == 4
    assert migrated["inventory"]["storage"] == []


def test_storage_roundtrip_and_merge():
    """仓库：同 id 消耗品合并堆叠，装备逐件，roundtrip 保数量。"""
    inv = Inventory()
    inv.storage_add(Item(id="2000000", name="红水", count=5, kind="consume"))
    inv.storage_add(Item(id="2000000", name="红水", count=3, kind="consume"))
    inv.storage_add(Item(id="01302000", name="木剑", kind="equip"))
    assert len(inv.storage) == 2
    assert inv.storage[0].count == 8

    inv2 = Inventory.from_dict(inv.to_dict(), assets=None)
    assert inv2.storage[0].count == 8
    assert inv2.storage[1].id == "01302000"
    assert inv2.storage[1].kind == "equip"


def test_save_manager_load_missing():
    """存檔不存在時 load 回傳 None。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nonexistent.json"
        sm = SaveManager(path)
        assert sm.load() is None


def test_save_manager_load_corrupted():
    """損壞的 JSON 回傳 None 不噴錯。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.json"
        path.write_text("{corrupted", encoding="utf-8")
        sm = SaveManager(path)
        assert sm.load() is None