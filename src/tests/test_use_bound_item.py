"""绑定到键的消耗品使用：按键即使用「这一种」物品并结算 hp/mp。

透过 Player.use_item_by_id 公开接口验证：只吃 consumes 表里的指定 id，
用完一堆自动消失，未知 id / 非消耗品返回 False 且不改状态。
"""

from __future__ import annotations

from game.entities.player import Player
from game.systems.inventory import Inventory, Item


class StubAssets:
    def __init__(self):
        self.equips = None
        self.job = 0

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def make_player(monkeypatch) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)

    def _init(self, assets, quest_defs=None):
        self.inventory = Inventory()
        self.max_hp, self.max_mp = 100, 50
        self.hp, self.mp = 10, 10

    monkeypatch.setattr(Player, "_init_new_game", _init)
    return Player(StubAssets(), 0.0, 0.0)


def test_use_bound_item_heals_and_consumes(monkeypatch):
    p = make_player(monkeypatch)
    p.inventory.add(Item(id="2000000", name="红药", count=2, kind="consume",
                         info={"spec": {"hp": 60}}))
    assert p.use_item_by_id("2000000")
    assert p.hp == 70
    assert p.inventory.consumes["2000000"].count == 1


def test_use_bound_item_last_stack_removes_entry(monkeypatch):
    p = make_player(monkeypatch)
    p.inventory.add(Item(id="2000006", name="蓝药", count=1, kind="consume",
                         info={"spec": {"mp": 30}}))
    assert p.use_item_by_id("2000006")
    assert p.mp == 40
    assert "2000006" not in p.inventory.consumes


def test_use_bound_item_rejects_unknown_and_non_consume(monkeypatch):
    p = make_player(monkeypatch)
    assert not p.use_item_by_id("2000000")
    p.inventory.add(Item(id="4000000", name="木块", count=1, kind="etc"))
    assert not p.use_item_by_id("4000000")
    assert p.hp == 10
