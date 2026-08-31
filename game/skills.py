"""技能系统：从 Skill.wz 读取战士技能表，管理等级 / SP / 冷却 / 消耗。

· SkillDef：一个技能的静态数据（名称、图标、各等级 mpCon/damage/range/mobCount）。
· SkillBook：玩家运行时状态 —— 已学等级、可用 SP、冷却计时；等级决定数值。
  技能数据全部来自官方 Skill.wz/100.img（战士），伤害倍率 = level.damage / 100。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import settings
from .assets import Assets


class SkillDef:
    def __init__(self, skill_id: str, name: str, desc: str,
                 levels: List[dict], max_level: int):
        self.id = skill_id
        self.name = name
        self.desc = desc
        self.levels = levels                # 1..N 级数值表（index 0 = 1 级）
        self.max_level = max_level

    def lv(self, level: int) -> dict:
        """第 level 级数值表（越界取最高级）。"""
        if not self.levels:
            return {}
        return self.levels[min(max(level, 1), len(self.levels)) - 1]

    def stat(self, level: int, key: str, default=0):
        val = self.lv(level).get(key)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default


def load_skill_defs(assets: Assets, skill_ids: List[str]) -> Dict[str, SkillDef]:
    """从 Skill.wz/100.img（战士）解析指定技能的等级表与名称。"""
    defs: Dict[str, SkillDef] = {}
    try:
        img = assets.wz["Skill"].root.images.get("100.img")
        if img is None:
            return defs
        root = img.parse()
        # 技能名 / 描述来自 String.wz/Skill.img
        try:
            s_img = assets.wz["String"].root.images.get("Skill.img")
            s_root = s_img.parse() if s_img is not None else None
        except Exception:
            s_root = None
        for sid in skill_ids:
            node = root.get(f"skill/{sid}")
            if node is None:
                continue
            lv_node = node.get("level")
            levels: List[dict] = []
            if lv_node is not None:
                entries = sorted(
                    (c for c in lv_node.children()),
                    key=lambda c: int(c.name) if c.name.isdigit() else 0,
                )
                for e in entries:
                    levels.append({c.name: getattr(c, "value", None)
                                   for c in e.children()})
            name, desc = f"技能 {sid}", ""
            if s_root is not None:
                sn = s_root.get(sid)
                if sn is not None:
                    nm = sn.get("name")
                    de = sn.get("desc")
                    name = str(nm.value) if nm is not None else name
                    desc = str(de.value) if de is not None else ""
            max_lv = min(len(levels), settings.SKILL_MAX_LEVEL)
            defs[sid] = SkillDef(sid, name, desc, levels[:max_lv], max_lv)
    except Exception:
        pass
    return defs


class SkillBook:
    """玩家技能状态：等级 / SP / 冷却。"""

    def __init__(self, assets: Assets):
        self.defs = load_skill_defs(assets, list(settings.SKILL_HOTKEYS.keys()))
        self.levels: Dict[str, int] = {}
        self.sp = 0
        self.cooldowns: Dict[str, float] = {}
        # 1 级自动赠送首个可学技能（魔天一擊），让开局就有技能体验
        first = next((sid for sid, lv in sorted(
            settings.SKILL_UNLOCK_LEVEL.items(), key=lambda kv: kv[1])), None)
        if first in self.defs:
            self.levels[first] = 1

    # ── 查询 ───────────────────────────────────────────────────────
    def known(self) -> List[str]:
        """已学技能 id（按解锁等级排序）。"""
        return sorted(self.levels, key=lambda s: settings.SKILL_UNLOCK_LEVEL.get(s, 99))

    def unlocked_for(self, level: int) -> List[str]:
        """当前玩家等级可学习但未学的技能。"""
        return [sid for sid, lv in settings.SKILL_UNLOCK_LEVEL.items()
                if level >= lv and sid not in self.levels]

    def can_learn(self, skill_id: str, player_level: int) -> bool:
        return (skill_id in self.defs
                and skill_id not in self.levels
                and player_level >= settings.SKILL_UNLOCK_LEVEL.get(skill_id, 99))

    # ── 学习 / 升级 ────────────────────────────────────────────────
    def learn_or_upgrade(self, skill_id: str, player_level: int) -> bool:
        """消耗 1 SP 学习或升级技能。返回是否成功。"""
        if self.sp <= 0:
            return False
        cur = self.levels.get(skill_id, 0)
        d = self.defs.get(skill_id)
        if d is None or cur >= d.max_level:
            return False
        if cur == 0 and not self.can_learn(skill_id, player_level):
            return False
        self.sp -= 1
        self.levels[skill_id] = cur + 1
        return True

    def gain_sp(self, amount: int) -> None:
        self.sp += amount

    # ── 施放 ───────────────────────────────────────────────────────
    def cast(self, skill_id: str, player_level: int) -> Optional[dict]:
        """尝试施放：返回施放数据（消耗 + 倍率 + 范围），失败返回 None。"""
        d = self.defs.get(skill_id)
        if d is None:
            return None
        lv = self.levels.get(skill_id, 0)
        if lv <= 0:
            return None
        if self.cooldowns.get(skill_id, 0.0) > 0.0:
            return None
        data = d.lv(lv)
        self.cooldowns[skill_id] = settings.SKILL_COOLDOWN.get(skill_id, 0.8)
        return {
            "id": skill_id,
            "def": d,
            "level": lv,
            "mp_con": d.stat(lv, "mpCon", 0),
            "hp_con": d.stat(lv, "hpCon", 0),
            "damage": d.stat(lv, "damage", 100) / 100.0,
            "range": d.stat(lv, "range", 0),          # 0 = 默认普攻范围
            "mob_count": d.stat(lv, "mobCount", 1),
        }

    def tick(self, dt: float) -> None:
        for sid in list(self.cooldowns):
            self.cooldowns[sid] -= dt
            if self.cooldowns[sid] <= 0:
                del self.cooldowns[sid]

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"sp": self.sp, "levels": dict(self.levels)}

    def from_dict(self, data: dict) -> None:
        self.sp = data.get("sp", 0)
        self.levels = dict(data.get("levels", {}))
        self.cooldowns.clear()
