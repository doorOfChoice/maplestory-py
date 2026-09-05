"""消耗品使用门控：满血拒用、百分比药、回程卷轴（透过公开接口验证）。

seam：Player.use_item_by_id / Player.try_use_consume；
不依赖 WZ，全部用合成 spec 构造消耗品。
"""

from __future__ import annotations

from game.entities.player import Player
from game.systems.inventory import Inventory, Item


class StubAssets:
    job = 0

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


def test_hp_full_rejects_potion_without_consuming(monkeypatch):
    p = make_player(monkeypatch)
    p.hp = 100
    p.inventory.add(Item(id="2000000", name="红药", count=2, kind="consume",
                         info={"spec": {"hp": 60}}))
    assert not p.use_item_by_id("2000000")
    assert p.inventory.consumes["2000000"].count == 2


def test_percent_potion_heals_by_max_ratio(monkeypatch):
    p = make_player(monkeypatch)
    p.inventory.add(Item(id="2000003", name="药丸", count=1, kind="consume",
                         info={"spec": {"hpR": 50, "mpR": 100}}))
    assert p.use_item_by_id("2000003")
    assert p.hp == 60       # 10 + 100×50%
    assert p.mp == 50       # 10 + 50×100%，钳到上限


def test_mixed_potion_usable_when_only_one_vital_missing(monkeypatch):
    p = make_player(monkeypatch)
    p.hp, p.mp = 100, 20
    p.inventory.add(Item(id="2000006", name="混合药", count=1, kind="consume",
                         info={"spec": {"hp": 60, "mp": 30}}))
    assert p.use_item_by_id("2000006")
    assert p.hp == 100      # 满血不溢出
    assert p.mp == 50       # 只补蓝


def test_no_effect_consume_rejected_without_consuming(monkeypatch):
    """弹药/宠物食品等无已实现效果的消耗品：拒用且不吞物品（旧 bug）。"""
    p = make_player(monkeypatch)
    p.inventory.add(Item(id="2022153", name="宠物食品", count=1,
                         kind="consume", info={"spec": {"time": 60}}))
    assert not p.use_item_by_id("2022153")
    assert p.inventory.consumes["2022153"].count == 1


def test_return_scroll_warps_and_consumes(monkeypatch):
    p = make_player(monkeypatch)
    warped: list[int] = []
    p.on_warp = lambda move_to: warped.append(move_to) or None
    p.inventory.add(Item(id="02030001", name="勇士之村回程卷轴", count=2,
                         kind="consume", info={"spec": {"moveTo": 104000000}}))
    assert p.use_item_by_id("02030001")
    assert warped == [104000000]
    assert p.inventory.consumes["02030001"].count == 1


def test_return_scroll_not_consumed_when_warp_refused(monkeypatch):
    p = make_player(monkeypatch)
    p.on_warp = lambda move_to: "此地图无法使用回程卷轴"
    p.inventory.add(Item(id="02030000", name="回程卷轴", count=1,
                         kind="consume", info={"spec": {"moveTo": 999999999}}))
    assert not p.use_item_by_id("02030000")
    assert p.inventory.consumes["02030000"].count == 1


def test_return_scroll_needs_warp_handler(monkeypatch):
    """Game 未接线（on_warp=None）：拒用且不扣卷轴。"""
    p = make_player(monkeypatch)
    p.inventory.add(Item(id="02030000", name="回程卷轴", count=1,
                         kind="consume", info={"spec": {"moveTo": 100000000}}))
    assert not p.use_item_by_id("02030000")
    assert p.inventory.consumes["02030000"].count == 1
