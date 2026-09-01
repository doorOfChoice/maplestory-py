"""怪物异常技能：skill 节点解析（毒/晕/减速）+ 接触命中概率触发。"""
from __future__ import annotations

from game.buffs import StatusList
from game.combat import Combat
from game.monster import parse_mob_status_skills


class Prop:
    """WZ 标量属性桩：只有 value。"""

    def __init__(self, value=None):
        self.value = value


class SkillEntry:
    """skill 节点的一个子项：键为 skill id，内含 level/prob。"""

    def __init__(self, name: str, level: int, prob: int = 100):
        self.name = name
        self._level = level
        self._prob = prob

    def get(self, key: str):
        if key == "level":
            return Prop(self._level)
        if key == "prob":
            return Prop(self._prob)
        return None


class SkillNode:
    """合成 mob skill 节点：skill/<id> → {level, prob}。"""

    def __init__(self, skills: dict):
        self._entries = [SkillEntry(sid, d["level"], d.get("prob", 100))
                         for sid, d in skills.items()]

    def children(self):
        return self._entries


def test_parse_keeps_only_known_status_skills():
    """毒(125)/晕(123)/减速(126) 保留并读出 level/prob；未知 id 忽略。"""
    node = SkillNode({"125": {"level": 1, "prob": 50},
                      "123": {"level": 3},
                      "100": {"level": 5, "prob": 80}})
    assert parse_mob_status_skills(node) == [("123", 3, 100), ("125", 1, 50)]


def test_parse_ignores_missing_level():
    """无 level 的 skill 条目忽略。"""
    node = SkillNode({"125": {"level": 0}})
    assert parse_mob_status_skills(node) == []


def test_parse_none_returns_empty():
    """怪物无 skill 节点返回空表。"""
    assert parse_mob_status_skills(None) == []


class FakePlayer:
    """合成玩家：记录 statuses 是否被施加。"""

    def __init__(self):
        self.statuses = StatusList()
        self.x = 100.0
        self.y = 100.0

    def hurt(self, from_x):
        return True

    def damage(self, amount):
        pass

    def defense_value(self):
        return 0


def test_contact_hit_applies_poison_when_prob_hits():
    """接触命中：prob=100 的毒异常必上（时长/强度来自 hit 里的预解析数据）。"""
    combat = Combat(None)
    player = FakePlayer()
    hits = [{"x": 0, "amount": 10, "status_attacks": [
        {"kind": "poison", "prob": 100, "duration": 5.0, "potency": 8.0}]}]
    combat.apply_mob_hits(player, hits)
    assert player.statuses.has("poison")
    st = player.statuses.active()[0]
    assert st.remaining == 5.0
    assert st.potency == 8.0


def test_contact_hit_skips_status_when_prob_misses():
    """prob=0：异常不上。"""
    combat = Combat(None)
    player = FakePlayer()
    hits = [{"x": 0, "amount": 10, "status_attacks": [
        {"kind": "stun", "prob": 0, "duration": 2.0, "potency": 0.0}]}]
    combat.apply_mob_hits(player, hits)
    assert not player.statuses.locked()
    assert player.statuses.active() == []
