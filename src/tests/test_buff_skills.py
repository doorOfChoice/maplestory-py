"""Buff 技能施放接线：cast 出含 time 字段的技能 → player.buffs 生效、面板变化。

seam：Player.start_attack（buff 施放入口）+ 各面板数值函数；全部用合成 SkillDef，
字段名沿用真实 Skill.wz（pad/acc/eva/x/y 等），不依赖 WZ。
"""
from __future__ import annotations

from game.systems.inventory import Inventory, Item
from game.entities.player import Player
from game.systems.skills import SkillBook, SkillDef
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


def _buff_init(self, assets, quest_defs=None):
    """最小新档初始化：真实 Inventory/SkillBook（attack_value 需要）。"""
    self.inventory = Inventory()
    # 固定发一把 PAD=25 的武器：面板算式不随空手基准 BASE_WEAPON_PAD 漂移
    self.inventory.equipped["weapon"] = Item(
        id="01302000", name="木剑", kind="equip",
        info={"islot": "Wp", "incPAD": 25})
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
    """构造 buff 接线专用的 Player：桩掉动画与新档初始化。"""
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _buff_init)
    return Player(StubAssets(), 0.0, 0.0)


def make_skill(sid: str, name: str, **lv1) -> SkillDef:
    return SkillDef(sid, name, "", [dict(lv1)], 1)


def make_cast(sid: str, d: SkillDef, mp_con: int = 0) -> dict:
    return {"id": sid, "def": d, "level": 1, "mp_con": mp_con, "hp_con": 0,
            "damage": 1.0, "range": 0, "mob_count": 1, "bullet_count": 1}


def test_buff_pad_adds_flat_attack(monkeypatch):
    """念力集中(3121008)：pad=26 作为平坦物攻加值入面板，而非百分比。"""
    player = make_player(monkeypatch)
    before = player.attack_value()
    d = make_skill("3121008", "念力集中", time=240, pad=26)
    assert player.start_attack(make_cast("3121008", d, mp_con=10)) is True
    assert player.buffs.mod_sum("atk") == 26
    assert player.attack_value() == before + 26


def test_buff_accuracy_adds_flat_accuracy(monkeypatch):
    """集中術(3001003)：acc=20（WZ）作为平坦命中入面板。"""
    player = make_player(monkeypatch)
    before = player.accuracy_value()
    d = make_skill("3001003", "集中術", time=300, acc=20, eva=20)
    assert player.start_attack(make_cast("3001003", d, mp_con=8)) is True
    assert player.buffs.mod_sum("acc_flat") == 20
    assert player.accuracy_value() == before + 20
    assert player.evasion_value() >= 20


def test_buff_maple_blessing_raises_all_stats_percent(monkeypatch):
    """楓葉祝福(3121000)：x=50 → 四维 ×1.5。"""
    player = make_player(monkeypatch)
    player.stats["dex"] = 100
    before = player.total_stats()["dex"]
    d = make_skill("3121000", "楓葉祝福", time=900, x=50)
    assert player.start_attack(make_cast("3121000", d, mp_con=30)) is True
    assert player.buffs.mod_sum("stat_pct") == 50
    assert player.total_stats()["dex"] == int(before * 1.5)


def test_buff_sharp_eyes_raises_crit_and_crit_mult(monkeypatch):
    """會心之眼(3121002)：x=15 暴击率、y=140 暴伤 1.4。"""
    player = make_player(monkeypatch)
    d = make_skill("3121002", "會心之眼", time=300, x=15, y=140)
    assert player.start_attack(make_cast("3121002", d, mp_con=20)) is True
    assert player.crit_rate() == 15
    assert player.crit_mult() == 1.4


def test_buff_skill_consumes_mp_without_entering_attack(monkeypatch):
    """Buff 施放只扣 MP、不进入攻击状态（不挥击不产生 pending_skill）。"""
    player = make_player(monkeypatch)
    mp_before = player.mp
    d = make_skill("3001003", "集中術", time=70, acc=5)
    assert player.start_attack(make_cast("3001003", d, mp_con=8)) is True
    assert player.mp == mp_before - 8
    assert not player.attacking
    assert player.pending_skill is None


def test_damage_skill_does_not_apply_buff(monkeypatch):
    """无 time 字段的技能照常攻击，不产生 buff。"""
    player = make_player(monkeypatch)
    d = SkillDef("3001004", "斷魂箭", "", [{"damage": 190}], 1)
    data = {"id": "3001004", "def": d, "level": 1, "mp_con": 7, "hp_con": 0,
            "damage": 1.9, "range": 0, "mob_count": 1, "bullet_count": 1}
    assert player.start_attack(data) is True
    assert player.buffs.active() == []
    assert player.attacking


def test_attack_skill_with_time_field_still_attacks(monkeypatch):
    """带持续计时但含攻击属性的技能（烈火箭 damage+time）必须进攻击流程。"""
    player = make_player(monkeypatch)
    d = SkillDef("3111003", "烈火箭", "", [{"damage": 127, "time": 10}], 1)
    data = {"id": "3111003", "def": d, "level": 1, "mp_con": 25, "hp_con": 0,
            "damage": 1.27, "range": 0, "mob_count": 5, "bullet_count": 1}
    assert player.start_attack(data) is True
    assert player.attacking
    assert player.pending_skill is data
    assert player.buffs.active() == []


def test_multi_target_skill_with_time_field_still_attacks(monkeypatch):
    """无 damage 字段但有 mobCount 的多体技能（炸弹箭）同样不得被 buff 吞掉。"""
    player = make_player(monkeypatch)
    d = SkillDef("3101005", "炸弹箭", "", [{"mobCount": 5, "time": 4}], 1)
    data = {"id": "3101005", "def": d, "level": 1, "mp_con": 28, "hp_con": 0,
            "damage": 1.0, "range": 0, "mob_count": 5, "bullet_count": 1}
    assert player.start_attack(data) is True
    assert player.attacking
    assert player.buffs.active() == []
