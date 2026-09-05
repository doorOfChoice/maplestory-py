"""攻击后摇可被下一击取消 + 施放冷却与 cast 解耦（放不出来不白扣 CD）。"""
from __future__ import annotations

from game import settings
from game.entities.player import Player
from game.systems.inventory import Inventory, Item
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


def _init(self, assets, quest_defs=None):
    self.inventory = Inventory()
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
    """无动画帧的 Player：手动控制 attack_elapsed 与命中标志。"""
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _init)
    return Player(StubAssets(), 0.0, 0.0)


def make_def(sid: str, **lv1) -> SkillDef:
    return SkillDef(sid, "技能", "", [dict(lv1) or {"damage": 100}], 1)


def make_skill_cast() -> dict:
    d = SkillDef("3001004", "技能", "", [{"damage": 190}], 1)
    return {"id": "3001004", "def": d, "level": 1, "mp_con": 0, "hp_con": 0,
            "damage": 1.9, "range": 0, "mob_count": 1, "bullet_count": 1}


def book_with(*defs: SkillDef) -> SkillBook:
    return SkillBook(None, 3000, defs={d.id: d for d in defs})


# ── 攻击取消 ─────────────────────────────────────────────────────

def test_attack_locked_until_hit_settled(monkeypatch):
    """普攻命中未结算前（起手首帧内），技能也放不出来。"""
    player = make_player(monkeypatch)
    assert player.start_attack() is True
    player.attack_elapsed = settings.ATTACK_CANCEL_DELAY
    assert player.attack_slot_free(for_skill=True) is False
    assert player.start_attack(make_skill_cast()) is False


def test_settled_attack_locked_within_min_cancel_delay(monkeypatch):
    """命中已结算但未过最短取消时间，仍不可取消普攻后摇。"""
    player = make_player(monkeypatch)
    player.start_attack()
    player.attack_hit_applied = True
    player.attack_elapsed = settings.ATTACK_CANCEL_DELAY - 0.1
    assert player.attack_slot_free(for_skill=True) is False


def test_skill_cancels_normal_attack_after_min_delay(monkeypatch):
    """技能取消普攻后摇：命中结算 + 过了最短取消时间 → 直接接管并重置计时。"""
    player = make_player(monkeypatch)
    player.start_attack()
    player.attack_hit_applied = True
    player.attack_elapsed = settings.ATTACK_CANCEL_DELAY
    assert player.attack_slot_free(for_skill=True) is True
    assert player.start_attack(make_skill_cast()) is True
    assert player.attack_elapsed == 0.0
    assert player.attacking is True


def test_skill_recovery_never_cancellable(monkeypatch):
    """技能动画必须完整播完：普攻、其他技能都不得取消，防止双技交替提速。"""
    player = make_player(monkeypatch)
    player.start_attack(make_skill_cast())
    player.attack_hit_applied = True
    player.attack_elapsed = settings.ATTACK_CANCEL_DELAY
    assert player.attack_slot_free() is False
    assert player.attack_slot_free(for_skill=True) is False
    assert player.start_attack() is False
    assert player.start_attack(make_skill_cast()) is False


def test_normal_attack_never_cancels_recovery(monkeypatch):
    """普攻不可取消后摇（攻速仍由完整动画时长决定），即便命中早已结算。"""
    player = make_player(monkeypatch)
    player.start_attack()
    player.attack_hit_applied = True
    player.attack_elapsed = settings.ATTACK_CANCEL_DELAY
    assert player.attack_slot_free() is False
    assert player.start_attack() is False


def test_projectile_spawn_counts_as_settled(monkeypatch):
    """远程/弹道普攻以弹道生成为结算点（近战命中框不适用）。"""
    player = make_player(monkeypatch)
    player.start_attack()
    player.attack_projectile_spawned = True
    player.attack_elapsed = settings.ATTACK_CANCEL_DELAY
    assert player.attack_slot_free(for_skill=True) is True


def test_skill_cast_not_blocked_by_other_skill_cooldown(monkeypatch):
    """冷却按技能各自计算：A 的 CD 不挡 B。"""
    player = make_player(monkeypatch)
    book = player.skills
    book.defs["3001004"] = make_def("3001004", mpCon=0, damage=190)
    book.defs["3001005"] = make_def("3001005", mpCon=0, damage=92)
    book.levels["3001004"] = 1
    book.levels["3001005"] = 1
    d = book.cast("3001004", 1)
    assert d is not None
    book.start_cooldown("3001004")
    assert book.cast("3001004", 1) is None
    assert book.cast("3001005", 1) is not None


# ── cast 无副作用 ────────────────────────────────────────────────

def test_cast_does_not_consume_cooldown():
    """cast 只校验不写 CD；显式 start_cooldown 后才进冷却。"""
    book = book_with(make_def("3001004", mpCon=7, damage=190))
    book.levels["3001004"] = 1
    assert book.cast("3001004", 10) is not None
    assert book.cast("3001004", 10) is not None
    book.start_cooldown("3001004")
    assert book.cast("3001004", 10) is None
    book.tick(10.0)
    assert book.cast("3001004", 10) is not None
