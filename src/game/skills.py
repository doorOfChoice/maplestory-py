"""技能系统：按职业树加载技能表，管理等级 / SP / 冷却 / 消耗 / 快捷键。

· SkillDef：一个技能的静态数据（名称、各等级 mpCon/damage/bulletCount/mobCount、
  前置 req、学习所需人物等级 CharLevel、invisible 标记）。
· SkillBook：玩家运行时状态 —— 只加载当前职业树（新手 → 零技能）。
  学习受四重门控：SP > 0、前置 req 满足、CharLevel 满足、未满级。
  转职时 on_advance 把职业附赠被动直接满级，并为主动技能排布快捷键。
  技能数据全部来自官方 Skill.wz，伤害倍率 = level.damage / 100。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import settings
from .jobs import resolve_skill_img, skill_ids_for_job
from .localize import to_simplified


class SkillDef:
    def __init__(self, skill_id: str, name: str, desc: str,
                 levels: List[dict], max_level: int,
                 req: Optional[Dict[str, int]] = None,
                 char_level: int = 0, invisible: bool = False):
        self.id = skill_id
        self.name = name
        self.desc = desc
        self.levels = levels                # 1..N 级数值表（index 0 = 1 级）
        self.max_level = max_level
        self.req = req or {}                # 前置技能 {skill_id: 所需等级}
        self.char_level = char_level        # 学习所需人物等级
        self.invisible = invisible          # 职业自动附赠被动（不可手学）

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


def load_skill_defs(assets, skill_ids: List[str]) -> Dict[str, SkillDef]:
    """从 Skill.wz（按 id 前缀分图）解析指定技能的等级表、名称与学习条件。"""
    defs: Dict[str, SkillDef] = {}
    try:
        # 技能名 / 描述来自 String.wz/Skill.img
        try:
            s_img = assets.wz["String"].root.images.get("Skill.img")
            s_root = s_img.parse() if s_img is not None else None
        except Exception:
            s_root = None
        by_img: Dict[str, List[str]] = {}
        for sid in skill_ids:
            by_img.setdefault(resolve_skill_img(sid), []).append(sid)
        for img_name, sids in by_img.items():
            try:
                img = assets.wz["Skill"].root.images.get(img_name)
                if img is None:
                    continue
                root = img.parse()
            except Exception:
                continue
            for sid in sids:
                node = root.get(f"skill/{sid}")
                if node is None:
                    continue
                levels: List[dict] = []
                lv_node = node.get("level")
                if lv_node is not None:
                    entries = sorted(
                        (c for c in lv_node.children()),
                        key=lambda c: int(c.name) if c.name.isdigit() else 0,
                    )
                    for e in entries:
                        levels.append({c.name: getattr(c, "value", None)
                                       for c in e.children()})
                req: Dict[str, int] = {}
                req_node = node.get("req")
                if req_node is not None:
                    for c in req_node.children():
                        try:
                            req[str(int(c.name))] = int(getattr(c, "value", 1))
                        except (TypeError, ValueError):
                            continue
                char_lv = 0
                cl = node.get("CharLevel")
                if cl is not None:
                    try:
                        char_lv = int(cl.value)
                    except (TypeError, ValueError):
                        char_lv = 0
                inv_node = node.get("invisible")
                invisible = False
                if inv_node is not None:
                    try:
                        invisible = int(getattr(inv_node, "value", 1)) != 0
                    except (TypeError, ValueError):
                        invisible = True
                name, desc = f"技能 {sid}", ""
                if s_root is not None:
                    sn = s_root.get(sid)
                    if sn is not None:
                        nm = sn.get("name")
                        de = sn.get("desc")
                        name = to_simplified(str(nm.value)) if nm is not None else name
                        desc = to_simplified(str(de.value)) if de is not None else ""
                max_lv = min(len(levels), settings.SKILL_MAX_LEVEL)
                defs[sid] = SkillDef(sid, name, desc, levels[:max_lv], max_lv,
                                     req=req, char_level=char_lv,
                                     invisible=invisible)
    except Exception:
        pass
    return defs


class SkillBook:
    """玩家技能状态：等级 / SP / 冷却 / 快捷键。只含当前职业技能树。"""

    def __init__(self, assets, job: int,
                 defs: Optional[Dict[str, SkillDef]] = None):
        if defs is None:
            defs = load_skill_defs(assets, skill_ids_for_job(assets, job)) \
                if assets is not None else {}
        self.defs = defs
        self.job = job
        self.levels: Dict[str, int] = {}
        self.sp = 0
        self.cooldowns: Dict[str, float] = {}
        self.hotkeys: Dict[int, str] = {}       # 数字键 → 技能 id
        self._passive_ids: set = set()

    # ── 查询 ───────────────────────────────────────────────────────
    def known(self) -> List[str]:
        """已学技能 id（按 id 排序）。"""
        return sorted(self.levels)

    def learnable(self) -> List[str]:
        """本职业可手动学习的技能（排除 invisible 附赠被动）。"""
        return sorted(sid for sid, d in self.defs.items() if not d.invisible)

    # ── 学习 / 升级 ────────────────────────────────────────────────
    def learn(self, skill_id: str, player_level: int) -> bool:
        """消耗 1 SP 学习或升级。四重门控：SP / 前置 req / CharLevel / 未满级。"""
        if self.sp <= 0:
            return False
        d = self.defs.get(skill_id)
        if d is None or d.invisible:
            return False
        cur = self.levels.get(skill_id, 0)
        if cur >= d.max_level:
            return False
        if player_level < d.char_level:
            return False
        for rid, rlv in d.req.items():
            if self.levels.get(rid, 0) < rlv:
                return False
        self.sp -= 1
        self.levels[skill_id] = cur + 1
        self._assign_hotkey(skill_id)
        return True

    def _assign_hotkey(self, skill_id: str) -> None:
        """主动技能未上键时补入最小空闲数字键。"""
        if skill_id in self._passive_ids:
            return
        if skill_id in self.hotkeys.values():
            return
        used = set(self.hotkeys)
        key = next((k for k in range(1, 13) if k not in used), None)
        if key is not None:
            self.hotkeys[key] = skill_id

    def gain_sp(self, amount: int) -> None:
        self.sp += amount

    def passive_mods(self) -> Dict[str, int]:
        """已学被动技能的聚合属性修正。

        键：str/dex/int/luk/atk/def/crit/crit_mult/acc/range/hp/mp。
        被动技能在转职 on_advance 时已满级（invisible 附赠），这里读取
        Skill.wz level 表的真实字段映射：
            prop   → crit（暴击率 %，如霸王箭 12→40）
            damage → crit_mult（暴击伤害 %，如霸王箭 105→200）
            x      → acc（命中，如精準強化 1→16）
            range  → range（射程加成，如百步穿楊 15→120）
        player.total_stats / attack_value / defense_value / crit_rate 会读取本表。
        """
        mods: Dict[str, int] = {}
        for pid in self._passive_ids:
            d = self.defs.get(pid)
            lv = self.levels.get(pid, 0)
            if d is None or lv <= 0:
                continue
            lv_table = d.stat(lv, "prop", 0)
            if lv_table:
                mods["crit"] = mods.get("crit", 0) + lv_table
            lv_dmg = d.stat(lv, "damage", 0)
            if lv_dmg:
                mods["crit_mult"] = lv_dmg
            lv_x = d.stat(lv, "x", 0)
            if lv_x:
                mods["acc"] = mods.get("acc", 0) + lv_x
            lv_r = d.stat(lv, "range", 0)
            if lv_r:
                mods["range"] = mods.get("range", 0) + lv_r
            for stat_key, src in (("dex", "dex"), ("str", "str"),
                                  ("hp", "hp"), ("mp", "mp"),
                                  ("atk", "attack"), ("def", "pdd")):
                val = d.stat(lv, src, 0)
                if val:
                    mods[stat_key] = mods.get(stat_key, 0) + val
        return mods

    def on_advance(self, jobdef) -> None:
        """转职：职业附赠被动直接满级（免费），主动技能重排快捷键。"""
        self._passive_ids = {str(p) for p in jobdef.passive_ids}
        for pid in self._passive_ids:
            d = self.defs.get(pid)
            if d is not None:
                self.levels[pid] = d.max_level
        self.hotkeys = {}
        for sid in sorted(self.defs):
            if sid not in self._passive_ids and not self.defs[sid].invisible:
                self._assign_hotkey(sid)

    # ── 施放 ───────────────────────────────────────────────────────
    def cast(self, skill_id: str, player_level: int) -> Optional[dict]:
        """尝试施放：返回施放数据（消耗 + 倍率 + 弹道参数），失败返回 None。"""
        d = self.defs.get(skill_id)
        if d is None:
            return None
        lv = self.levels.get(skill_id, 0)
        if lv <= 0:
            return None
        if self.cooldowns.get(skill_id, 0.0) > 0.0:
            return None
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
            "bullet_count": max(1, d.stat(lv, "bulletCount", 1)),
        }

    def tick(self, dt: float) -> None:
        for sid in list(self.cooldowns):
            self.cooldowns[sid] -= dt
            if self.cooldowns[sid] <= 0:
                del self.cooldowns[sid]

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"sp": self.sp, "levels": dict(self.levels),
                "hotkeys": {str(k): v for k, v in self.hotkeys.items()}}

    def from_dict(self, data: dict) -> None:
        self.sp = data.get("sp", 0)
        self.levels = dict(data.get("levels", {}))
        self.hotkeys = {int(k): str(v)
                        for k, v in data.get("hotkeys", {}).items()}
        self.cooldowns.clear()
