"""技能系统：按职业树加载技能表，管理等级 / SP / 冷却 / 消耗 / 快捷键。

· SkillDef：一个技能的静态数据（名称、各等级 mpCon/damage/bulletCount/mobCount、
  前置 req、学习所需人物等级 CharLevel、invisible 标记）。
· SkillBook：玩家运行时状态 —— 累积加载「当前职业 + 各前置职业」的技能树
  （原版行为：转职后保留旧职业技能）。学习受四重门控：该转 SP > 0、前置 req
  满足、CharLevel 满足、未满级。SP 按职业组分池独立结算（一转/二转/三转各自结余）。
  转职时 on_advance 把该转附赠被动直接满级（被动跨转累加进 passive_mods），
  并为已学主动技能重排快捷键。技能数据全部来自官方 Skill.wz，伤害倍率 = level.damage / 100。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from game import settings
from game.core.jobs import (job_chain, job_sp_group, resolve_skill_img,
                            skill_ids_for_chain, sp_group_of_skill)
from game.core.keybindings import SKILL_SLOT_COUNT
from game.core.localize import to_simplified


# 蜗牛投掷术：v113 TW 的 1000.img 该节点只有图标与名字、数值表为空，
# 按同系新手技能的量级合成 3 级数值（100%→120%，MP 消耗固定 4）。
_SNAIL_LEVELS = [{"mpCon": 4, "damage": 100 + 10 * i} for i in range(3)]


def apply_synthesized(defs: Dict[str, "SkillDef"], job: int) -> None:
    """把合成数值表并入技能定义（WZ 有名有图标、缺数值的新手树）。

    树里已有占位节点（职业链含新手、从 WZ 加载到）→ 补数值；
    新手期无 WZ（纯逻辑测试）→ 直接创建；其他职业的显式 defs 不受污染。
    """
    sid = settings.SNAIL_THROW_SKILL_ID
    if sid in defs:
        d = defs[sid]
        d.levels = [dict(lv) for lv in _SNAIL_LEVELS]
        d.max_level = len(d.levels)
    elif job == 0:
        defs[sid] = SkillDef(sid, "蜗牛投掷术", "消耗MP向怪物投掷蜗牛。",
                             [dict(lv) for lv in _SNAIL_LEVELS],
                             len(_SNAIL_LEVELS))


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
    """玩家技能状态：累积各转技能树 / 逐转独立 SP 池 / 冷却 / 快捷键。"""

    def __init__(self, assets, job: int,
                 defs: Optional[Dict[str, SkillDef]] = None):
        if defs is None:
            defs = load_skill_defs(assets, skill_ids_for_chain(assets, job)) \
                if assets is not None else {}
        apply_synthesized(defs, job)
        self.defs = defs
        self.job = job
        self.levels: Dict[str, int] = {}
        self.sp_by_job: Dict[int, int] = {}       # SP 职业组（300/310/311）→ 结余
        self.cooldowns: Dict[str, float] = {}
        self.hotkeys: Dict[int, str] = {}          # 数字键 → 技能 id
        self._passive_ids: set = set()

    # ── 查询 ───────────────────────────────────────────────────────
    @property
    def total_sp(self) -> int:
        """跨转 SP 结余合计（状态面板展示用）。"""
        return sum(self.sp_by_job.values())

    def sp_for_group(self, group: int) -> int:
        return self.sp_by_job.get(group, 0)

    def known(self) -> List[str]:
        """已学技能 id（按 id 排序）。"""
        return sorted(self.levels)

    def learnable(self, owner_group: Optional[int] = None) -> List[str]:
        """可手动学习的技能（排除附赠被动与 invisible）；给定组则只回该转。"""
        return sorted(
            sid for sid, d in self.defs.items()
            if not d.invisible and sid not in self._passive_ids
            and (owner_group is None or sp_group_of_skill(sid) == owner_group))

    def skills_for_group(self, group: int) -> List[str]:
        """技能窗某转页签要展示的全部技能（含自动满级被动，按 id 排序）。"""
        return sorted(sid for sid in self.defs if sp_group_of_skill(sid) == group)

    # ── SP 结算 ────────────────────────────────────────────────────
    def add_sp(self, group: int, amount: int) -> None:
        """直接向某转 SP 池加值（内部/测试用）。"""
        if amount:
            self.sp_by_job[group] = self.sp_by_job.get(group, 0) + amount

    def gain_sp_for_level(self, level: int, amount: int) -> None:
        """升级加 SP：归入职业链中「解锁等级 ≤ 本等级」的最高一阶（原版逐转分池）。"""
        group = self._group_for_level(level)
        if group is not None:
            self.add_sp(group, amount)

    def _group_for_level(self, level: int) -> Optional[int]:
        chain = job_chain(self.job)
        best = None
        for jd in chain:
            if jd.advance_lv <= level and (best is None or jd.advance_lv >= best.advance_lv):
                best = jd
        if best is None and chain:
            best = chain[0]
        return job_sp_group(best.code) if best is not None else None

    # ── 学习 / 升级 ────────────────────────────────────────────────
    def learn(self, skill_id: str, player_level: int) -> bool:
        """消耗该转 1 SP 学习或升级。四重门控：SP / 前置 req / CharLevel / 未满级。"""
        if skill_id in self._passive_ids:
            return False
        group = sp_group_of_skill(skill_id)
        if self.sp_by_job.get(group, 0) <= 0:
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
        self.sp_by_job[group] -= 1
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

    def passive_mods(self) -> Dict[str, int]:
        """已学被动技能的聚合属性修正（跨转累加）。

        键：str/dex/int/luk/atk/def/crit/crit_mult/acc/range/hp/mp。
        被动技能在转职 on_advance 时已满级（附赠），这里读取
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
        """转职：本职业附赠被动满级（累加进 passive），重排全部主动快捷键。"""
        for p in jobdef.passive_ids:
            pid = str(p)
            self._passive_ids.add(pid)
            d = self.defs.get(pid)
            if d is not None:
                self.levels[pid] = d.max_level
        self.rebuild_hotkeys()

    def inherit(self, old: "SkillBook") -> None:
        """转职累积：把旧技能书的已学等级、各转 SP 结余、被动集合搬进本书。"""
        if old is None:
            return
        self.levels = dict(old.levels)
        self.sp_by_job = dict(old.sp_by_job)
        self._passive_ids = set(old._passive_ids)

    def rebuild_hotkeys(self) -> None:
        """为全部可学主动技能（含旧转已学）重排最小空闲数字键。"""
        self.hotkeys = {}
        for sid in sorted(self.defs):
            d = self.defs[sid]
            if sid in self._passive_ids or d.invisible:
                continue
            self._assign_hotkey(sid)

    # ── 施放 ───────────────────────────────────────────────────────
    def cast(self, skill_id: str, player_level: int) -> Optional[dict]:
        """校验并返回施放数据（消耗 + 倍率 + 弹道参数），失败返回 None。

        无副作用：不写冷却。确认出手成功后由调用方 start_cooldown。
        """
        d = self.defs.get(skill_id)
        if d is None:
            return None
        lv = self.levels.get(skill_id, 0)
        if lv <= 0:
            return None
        if self.cooldowns.get(skill_id, 0.0) > 0.0:
            return None
        data = {
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
        if skill_id == settings.SNAIL_THROW_SKILL_ID:
            data["projectile"] = True                  # 弹道技：不进近战命中框
            data["speed"] = settings.SNAIL_THROW_SPEED
            data["life"] = settings.SNAIL_THROW_LIFETIME
        return data

    def start_cooldown(self, skill_id: str) -> None:
        """确认出手后写入施放冷却（cast 本身无副作用）。"""
        self.cooldowns[skill_id] = settings.SKILL_COOLDOWN.get(skill_id, 0.8)

    def tick(self, dt: float) -> None:
        for sid in list(self.cooldowns):
            self.cooldowns[sid] -= dt
            if self.cooldowns[sid] <= 0:
                del self.cooldowns[sid]

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"sp_by_job": {str(k): v for k, v in self.sp_by_job.items()},
                "levels": dict(self.levels), "passives": sorted(self._passive_ids),
                "hotkeys": {str(k): v for k, v in self.hotkeys.items()}}

    def from_dict(self, data: dict) -> None:
        self.levels = dict(data.get("levels", {}))
        passives = data.get("passives")
        if passives is not None:
            self._passive_ids = {str(p) for p in passives}
        else:                                   # 旧档未存被动集：按职业链反推
            self._passive_ids = {str(pid) for jd in job_chain(self.job)
                                 for pid in jd.passive_ids
                                 if str(pid) in self.levels}
        raw_sp = data.get("sp_by_job")
        if raw_sp is not None:
            self.sp_by_job = {int(k): int(v) for k, v in raw_sp.items()}
        else:                                   # 旧档单一 sp → 归入当前职业组
            legacy = int(data.get("sp", 0) or 0)
            self.sp_by_job = {job_sp_group(self.job): legacy} if legacy else {}
        self.hotkeys = {int(k): str(v)
                        for k, v in data.get("hotkeys", {}).items()}
        self.cooldowns.clear()


def assign_skill_to_key(book: SkillBook, bindings, skill_id: str,
                        key: int) -> bool:
    """技能拖到键盘某键上：复用已上槽位或取最小空闲槽，再改绑该槽动作键。

    被占键的让位由 KeyBindings.set 的互换语义完成；未学 / 被动 / 槽满 / Esc
    一律拒绝且不留脏状态。
    """
    if skill_id not in book.levels or skill_id not in book.learnable():
        return False
    slot = next((k for k, v in book.hotkeys.items() if v == skill_id), None)
    if slot is None:
        slot = next((k for k in range(1, SKILL_SLOT_COUNT + 1)
                     if k not in book.hotkeys), None)
    if slot is None or not bindings.set(f"skill_{slot}", key):
        return False
    book.hotkeys[slot] = skill_id
    return True
