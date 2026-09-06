"""特效药（200xxxx 带 time + 属性键的 Consume）：使用后上百分比 buff 并改变面板。

seam：Player.use_item_by_id / Player.try_use_consume + 各面板数值函数；
全部用合成 spec，不依赖 WZ。数值语义按原版：spec 值 = 面板百分比加成。
"""

from __future__ import annotations

from game.systems.inventory import Inventory, Item
from game.entities.player import Player
from game.systems.skills import SkillBook
from game.core.stats import base_stats


class StubAssets:
    """最小资产桩：只补 Player 构造用到的 WZ 无关接口。"""

    def __init__(self):
        self.equips = None
        self.job = 0

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def _elixir_init(self, assets, quest_defs=None):
    """最小新档初始化：真实 Inventory/SkillBook（面板算式需要）。"""
    self.inventory = Inventory()
    self.inventory.equipped["weapon"] = Item(
        id="01302000", name="木剑", kind="equip",
        info={"islot": "Wp", "incPAD": 25, "incMAD": 20})
    self.skills = SkillBook(None, 0)
    self.quests = {}
    self.stats = base_stats()
    self.level = 1
    self.pending_skill = None
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


def make_player(monkeypatch) -> Player:
    """构造特效药测试专用的 Player：桩掉动画与新档初始化。"""
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _elixir_init)
    return Player(StubAssets(), 0.0, 0.0)


def add_consume(player: Player, item_id: str, name: str, spec: dict,
                count: int = 1) -> None:
    player.inventory.add(Item(id=item_id, name=name, count=count,
                              kind="consume", info={"spec": spec}))


def test_accuracy_elixir_applies_buff(monkeypatch):
    """命中药（acc+5 / time 300000ms）→ 上 300 秒 acc buff。"""
    p = make_player(monkeypatch)
    add_consume(p, "02002005", "命藥", {"acc": 5, "time": 300000})
    assert p.use_item_by_id("02002005")
    active = p.buffs.active()
    assert [b.skill_id for b in active] == ["02002005"]
    assert active[0].name == "命藥"
    assert active[0].total == 300.0


def test_accuracy_elixir_boosts_accuracy_panel(monkeypatch):
    """命中面板 ×(1+5%)。"""
    p = make_player(monkeypatch)
    before = p.accuracy_value()
    add_consume(p, "02002005", "命藥", {"acc": 5, "time": 300000})
    assert p.use_item_by_id("02002005")
    assert p.accuracy_value() == int(before * 1.05)


def test_attack_elixir_boosts_attack_range(monkeypatch):
    """力藥（pad+10）→ 攻击区间两端 ×1.10。"""
    p = make_player(monkeypatch)
    lo, hi = p.attack_range()
    add_consume(p, "02002004", "力藥", {"pad": 10, "time": 600000})
    assert p.use_item_by_id("02002004")
    assert p.attack_range() == (int(lo * 1.10), int(hi * 1.10))


def test_magic_attack_elixir_boosts_magic_panel(monkeypatch):
    """魔法藥（mad+10）→ 魔攻 ×1.10。"""
    p = make_player(monkeypatch)
    before = p.magic_attack_value()
    add_consume(p, "02002002", "魔法藥", {"mad": 10, "time": 180000})
    assert p.use_item_by_id("02002002")
    assert p.magic_attack_value() == int(before * 1.10)


def test_defense_elixirs_boost_both_defenses(monkeypatch):
    """护甲藥（pdd+30 / mdd+30）→ 物防魔防各 ×1.30。"""
    p = make_player(monkeypatch)
    pdef, mdef = p.defense_value(), p.magic_defense_value()
    add_consume(p, "02002011", "護甲藥",
                {"pdd": 30, "mdd": 30, "time": 1800000})
    assert p.use_item_by_id("02002011")
    assert p.defense_value() == int(pdef * 1.30)
    assert p.magic_defense_value() == int(mdef * 1.30)


def test_evasion_elixir_boosts_evasion_panel(monkeypatch):
    """回避藥（eva+5）→ 回避 ×1.05。"""
    p = make_player(monkeypatch)
    before = p.evasion_value()
    add_consume(p, "02002000", "回避藥", {"eva": 5, "time": 180000})
    assert p.use_item_by_id("02002000")
    assert p.evasion_value() == int(before * 1.05)


def test_speed_elixir_boosts_move_and_jump(monkeypatch):
    """速度藥（speed+10 / jump+10）→ 移速跳跃 ×1.10。"""
    p = make_player(monkeypatch)
    mv, jv = p.move_speed(), p.jump_velocity()
    add_consume(p, "02002010", "速度藥",
                {"speed": 10, "jump": 10, "time": 600000})
    assert p.use_item_by_id("02002010")
    assert p.move_speed() == mv * 1.10
    assert p.jump_velocity() == jv * 1.10


def test_elixir_buff_expires_after_duration(monkeypatch):
    """持续时间走完后 buff 消失、面板回落。"""
    p = make_player(monkeypatch)
    before = p.accuracy_value()
    add_consume(p, "02002005", "命藥", {"acc": 5, "time": 300000})
    p.use_item_by_id("02002005")
    p.buffs.tick(300.0)
    assert p.buffs.active() == []
    assert p.accuracy_value() == before


def test_healing_elixir_heals_and_buffs(monkeypatch):
    """复合藥（回血 + pad）：两者同时生效。"""
    p = make_player(monkeypatch)
    p.hp = 10
    lo, hi = p.attack_range()
    add_consume(p, "02002015", "複合藥",
                {"hpR": 90, "pad": 5, "pdd": 40, "time": 900000})
    assert p.use_item_by_id("02002015")
    assert p.hp == 100
    assert p.attack_range() == (int(lo * 1.05), int(hi * 1.05))


def test_full_hp_still_allows_buff_part(monkeypatch):
    """满血但含 buff 词条：不因回血无效而拒用。"""
    p = make_player(monkeypatch)
    add_consume(p, "02002015", "複合藥", {"hp": 60, "acc": 5, "time": 300000})
    assert p.use_item_by_id("02002015")
    assert p.buffs.mod_sum("acc") == 5


def test_time_only_consume_still_rejected(monkeypatch):
    """只有 time 无已实现属性键（如宠物食品）：依旧拒用不吞物品。"""
    p = make_player(monkeypatch)
    add_consume(p, "02022153", "宠物食品", {"time": 60}, count=1)
    assert not p.use_item_by_id("02022153")
    assert p.inventory.consumes["02022153"].count == 1


def test_debuff_elixir_lowers_panel(monkeypatch):
    """负面值（acc-5 / pad+20）：按符号生效。"""
    p = make_player(monkeypatch)
    acc_before, atk_before = p.accuracy_value(), p.attack_value()
    add_consume(p, "02022002", "烈酒",
                {"acc": -5, "pad": 20, "time": 180000})
    assert p.use_item_by_id("02022002")
    assert p.accuracy_value() == int(acc_before * 0.95)
    assert p.attack_value() == int(atk_before * 1.20)


def test_same_elixir_recasts_refreshes_duration(monkeypatch):
    """同种特效药重复使用 = 刷新持续时间，数值不叠加。"""
    p = make_player(monkeypatch)
    add_consume(p, "02002005", "命藥", {"acc": 5, "time": 300000}, count=2)
    p.use_item_by_id("02002005")
    p.buffs.tick(200.0)
    p.use_item_by_id("02002005")
    assert p.buffs.mod_sum("acc") == 5
    assert p.buffs.active()[0].remaining == 300.0
