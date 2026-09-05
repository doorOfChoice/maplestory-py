"""战斗明细接入结算：击杀产生经验条目、拾取成交产生金币/物品条目。"""

from __future__ import annotations

import pygame

from game import settings
from game.systems.combat import Combat, DropItem
from game.systems.inventory import Inventory


class _Mob:
    x, cy, sprite_h, level, pd = 10.0, 100.0, 30, 1, 0
    dead = False
    exp = 10
    mob_id = "100101"
    name = "蓝蜗牛"

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def take_hit(self, damage: int, from_x=None) -> bool:
        return True

    def roll_drop(self):
        return None


class _Player:
    x, y = 0.0, 100.0
    level = 10
    attack_hit_applied = False
    pending_skill = None
    inventory = Inventory()

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-10, 60, 60, 60)

    def attack_range(self):
        return (50, 50)

    def crit_rate(self) -> float:
        return 0.0

    def crit_mult(self) -> float:
        return 1.5


class _Assets:
    footholds: list = []

    def skill_hit_frames(self, sid):
        return []

    def item_name(self, item_id):
        return f"物品{item_id}"

    def item_icon(self, item_id):
        return pygame.Surface((8, 8))

    def equip_icon(self, item_id):
        return None


def test_kill_pushes_exp_entry_with_mob_name():
    """击杀成功：明细出一条 exp 条目，怪名与经验取自怪对象。"""
    c = Combat(_Assets())
    c.player_attack(_Player(), [_Mob()])
    assert [(e.kind, e.name, e.amount) for e in c.combat_log.entries] == \
        [("exp", "蓝蜗牛", 10)]


def test_zero_exp_kill_pushes_no_entry():
    """0 经验的怪不出条目。"""
    c = Combat(_Assets())
    mob = _Mob()
    mob.exp = 0
    c.player_attack(_Player(), [mob])
    assert c.combat_log.entries == []


def test_pickup_meso_pushes_meso_entry():
    """金币吸附成交：明细出一条 meso 条目，金额为拾取数。"""
    c = Combat(_Assets())
    p = _Player()
    d = DropItem(10.0, p.y, meso=12, ground_y=p.y)
    d._age = 99.0
    c.drops.append(d)
    c.pickup(p)
    c.update(0.25, p)
    assert [(e.kind, e.amount) for e in c.combat_log.entries] == [("meso", 12)]


def test_pickup_item_pushes_item_entry():
    """物品吸附成交：明细出一条 item 条目，键为归一化物品 id、数量为件数。"""
    c = Combat(_Assets())
    p = _Player()
    d = DropItem(10.0, p.y, item={"id": "4000000", "name": "蓝螺壳", "count": 2},
                 ground_y=p.y)
    d._age = 99.0
    c.drops.append(d)
    c.pickup(p)
    c.update(0.25, p)
    assert [(e.kind, e.key, e.name, e.amount) for e in c.combat_log.entries] == \
        [("item", "04000000", "蓝螺壳", 2)]
