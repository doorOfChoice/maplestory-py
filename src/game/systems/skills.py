"""技能系统：按职业树加载技能表，管理等级 / SP / 冷却 / 消耗 / 快捷键。

· SkillDef：一个技能的静态数据（名称、各等级 mpCon/damage/bulletCount/mobCount、
  前置 req、学习所需人物等级 CharLevel；invisible 只是原版 UI 隐藏标记
  ——4 转树大量标 invisible 但仍可学，故本项目不以其为门控）。
· SkillBook：玩家运行时状态 —— 累积加载「当前职业 + 各前置职业」的技能树
  （原版行为：转职后保留旧职业技能）。学习受四重门控：该转 SP > 0、前置 req
  满足、CharLevel 满足、未满级。SP 按职业组分池独立结算（一转/二转/三转各自结余）。
  转职时 on_advance 把该转附赠被动直接满级（被动跨转累加进 passive_mods）。
  快捷键永不自动分配：只有玩家把技能拖到键格上（assign_skill_to_key）才上键。
  技能数据全部来自官方 Skill.wz，伤害倍率 = level.damage / 100，
  冷却取 level.cooltime（秒），多段技取 level.attackCount。
· 施放形态（交付方式）与效果载荷由分面模型统一表达：core.skill_semantics 按
  WZ 顶层节点 + level 字段推导交付方式（kind），并产出效果子句列表
  （core.skill_spec：Damage/Buff/Debuff/Heal/Summon/Field/Move/Proc/Cleanse…）。
  新增技能默认零改动；只有 x/y/prop/damage 等同名字段不同义时才进声明式例外表。
  被动/buff 的 WZ 字段语义差异由 core.skill_effects 统一翻译（见该模块）。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from game import settings
from game.core import skill_effects, skill_semantics, skill_spec
from game.core.jobs import (job_chain, job_sp_group, resolve_skill_img,
                            skill_ids_for_chain, sp_group_of_skill)
from game.core.keybindings import SKILL_SLOT_COUNT
from game.core.localize import to_simplified


# 蜗牛投掷术：v113 TW 的 1000.img 该节点只有图标与名字、数值表为空，
# 按同系新手技能的量级合成 3 级数值（100%→120%，MP 消耗固定 4）。
_SNAIL_LEVELS = [{"mpCon": 4, "damage": 100 + 10 * i} for i in range(3)]

# 魔力恢復(2000000)：v113 的 200.img level 表只有 hs 字符串、无数值字段，
# 按原版「自然回蓝随等级提升」合成 mp_regen（0.1/s 点数，每级 +2 → 满级 16 级 +3.2/s）。
_MAGIC_RECOVERY_SKILL_ID = "2000000"
_MAGIC_RECOVERY_LEVELS = [{"mp_regen": 2 * (i + 1)} for i in range(16)]


def _install(defn: "SkillDef", levels: list) -> None:
    defn.levels = [dict(lv) for lv in levels]
    defn.max_level = len(levels)


def apply_synthesized(defs: Dict[str, "SkillDef"], job: int) -> None:
    """把合成数值表并入技能定义（WZ 有名有图标、缺数值的技能）。

    树里已有占位节点（从 WZ 加载到）→ 补数值；
    新手期无 WZ（纯逻辑测试）→ 直接创建；其他职业的显式 defs 不受污染。
    """
    sid = settings.SNAIL_THROW_SKILL_ID
    if sid in defs:
        _install(defs[sid], _SNAIL_LEVELS)
    elif job == 0:
        defs[sid] = SkillDef(sid, "蜗牛投掷术", "消耗MP向怪物投掷蜗牛。",
                             [dict(lv) for lv in _SNAIL_LEVELS],
                             len(_SNAIL_LEVELS))
    if _MAGIC_RECOVERY_SKILL_ID in defs:
        _install(defs[_MAGIC_RECOVERY_SKILL_ID], _MAGIC_RECOVERY_LEVELS)


class SkillDef:
    def __init__(self, skill_id: str, name: str, desc: str,
                 levels: List[dict], max_level: int,
                 req: Optional[Dict[str, int]] = None,
                 char_level: int = 0, invisible: bool = False,
                 repeat: bool = False, has_ball: bool = False,
                 has_hit: bool = False, has_mob_icon: bool = False,
                 action: str = "", helps: Optional[Dict[int, str]] = None,
                 element: str = "", has_summon: bool = False,
                 has_keydown: bool = False, has_tile: bool = False,
                 has_affected: bool = False, has_state: bool = False,
                 skill_type: int = 0, master_level: int = 0):
        self.id = skill_id
        self.name = name
        self.desc = desc
        self.levels = levels                # 1..N 级数值表（index 0 = 1 级）
        self.max_level = max_level
        self.req = req or {}                # 前置技能 {skill_id: 所需等级}
        self.char_level = char_level        # 学习所需人物等级
        self.invisible = invisible          # WZ 原版 UI 隐藏标记（不挡学习）
        self.repeat = repeat                # WZ 带 keydown 通道技（按住连发）
        self.has_ball = has_ball            # WZ 带 ball 节点：弹道技（非瞬发）
        self.has_hit = has_hit              # WZ 带 hit 节点：攻击技（time 可能是状态时长）
        self.has_mob_icon = has_mob_icon    # WZ 带 mob 节点：对怪上状态（debuff）
        self.action = action                # WZ action 节点：官方施法动作名
        self.element = element              # WZ elemAttr：技能元素字母（f/i/l/s/h/d）
        self.helps = dict(helps) if helps else {}   # 级别 → WZ 逐级说明（hs→String.wz hN）
        # ── 分面模型的 WZ 结构标记（交付方式推导用）──────────────────
        self.has_summon = has_summon        # WZ 带 summon 节点：召唤物
        self.has_keydown = has_keydown      # WZ 带 keydown 节点：引导通道技
        self.has_tile = has_tile            # WZ 带 tile 节点：地面/持续区域
        self.has_affected = has_affected    # WZ 带 affected 节点：团队/范围增益
        self.has_state = has_state          # WZ 带 state 节点：斗气等状态
        self.skill_type = skill_type        # WZ skillType：1 熟练 2 攻速 3 终极
        self.master_level = master_level    # WZ masterLevel：原版满级上限

    @property
    def spec(self) -> "skill_spec.SkillSpec":
        """该技能的分面描述（交付/代价/效果子句）。惰性构造，不缓存等级表。"""
        return skill_semantics.build_spec(self)

    def lv(self, level: int) -> dict:
        """第 level 级数值表（越界取最高级）。"""
        if not self.levels:
            return {}
        return self.levels[min(max(level, 1), len(self.levels)) - 1]

    def help(self, level: int) -> str:
        """第 level 级的 WZ 逐级说明文案（level.hs 指向 String.wz 的 hN）；无则空串。"""
        if level <= 0:
            return ""
        return self.helps.get(level, "")

    def stat(self, level: int, key: str, default=0):
        val = self.lv(level).get(key)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default


def skill_buff_seconds(d: "SkillDef", level: int) -> float:
    """纯 buff 持续秒数（非攻击才 >0）；实现见 core.skill_semantics。"""
    return skill_semantics.skill_buff_seconds(d, level)


def cast_form(d: "SkillDef", level: int) -> str:
    """技能交付方式（分面模型 kind）；实现见 core.skill_semantics.delivery。

    返回 skill_spec.DELIVERY_KINDS 之一：passive/heal/teleport/buff/projectile/
    instant/aoe/mob_status/summon/field/channel/aura/move/unsupported。
    """
    return skill_semantics.delivery(d, level)


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
                # WZ 带 keydown 动画节点 = 通道技（原版按住键以 keydown 帧连发，
                # 如暴風神射 3121004）；本项目用固定补放间隔模拟该行为
                repeat = node.get("keydown") is not None
                # WZ 带 ball 节点 = 发射弹道（魔法弹）；无 ball 的魔法攻击（双击）
                # 命中即结算、不生成飞行物
                has_ball = node.get("ball") is not None
                has_hit = node.get("hit") is not None
                has_mob_icon = node.get("mob") is not None
                # 分面模型结构标记：召唤 / 引导 / 地面 / 团体增益 / 状态
                has_summon = node.get("summon") is not None
                has_keydown = node.get("keydown") is not None
                has_tile = node.get("tile") is not None
                has_affected = node.get("affected") is not None
                has_state = node.get("state") is not None
                skill_type = 0
                st_node = node.get("skillType")
                if st_node is not None:
                    try:
                        skill_type = int(getattr(st_node, "value", 0))
                    except (TypeError, ValueError):
                        skill_type = 0
                master_level = 0
                ml_node = node.get("masterLevel")
                if ml_node is not None:
                    try:
                        master_level = int(getattr(ml_node, "value", 0))
                    except (TypeError, ValueError):
                        master_level = 0
                action = ""
                act_node = node.get("action/0")
                if act_node is not None:
                    action = str(getattr(act_node, "value", "") or "")
                # WZ elemAttr：技能元素（小写单字符 f/i/l/s/h/d），供属性克制结算
                element = ""
                elem_node = node.get("elemAttr")
                if elem_node is not None:
                    element = str(getattr(elem_node, "value", "") or "").strip().lower()
                name, desc = f"技能 {sid}", ""
                help_by_key: Dict[str, str] = {}
                if s_root is not None:
                    sn = s_root.get(sid)
                    if sn is not None:
                        nm = sn.get("name")
                        de = sn.get("desc")
                        name = to_simplified(str(nm.value)) if nm is not None else name
                        desc = to_simplified(str(de.value)) if de is not None else ""
                        # 逐级说明：String.wz 里 h1..hN，由 level.hs 引用
                        for hc in sn.children():
                            if hc.name[:1] == "h" and hc.name[1:].isdigit():
                                help_by_key[hc.name] = to_simplified(str(hc.value))
                max_lv = min(len(levels), settings.SKILL_MAX_LEVEL)
                # masterLevel 为原版该技能的真实满级上限（四转技常为 10/20），
                # 有值时优先取较小者；缺省（None/0）时沿用 level 表长度。
                if master_level > 0:
                    max_lv = min(max_lv, master_level)
                helps: Dict[int, str] = {}
                for i, lvtab in enumerate(levels[:max_lv]):
                    hs_key = lvtab.get("hs")
                    if hs_key is not None:
                        helps[i + 1] = help_by_key.get(str(hs_key), "")
                defs[sid] = SkillDef(sid, name, desc, levels[:max_lv], max_lv,
                                     req=req, char_level=char_lv,
                                     invisible=invisible, repeat=repeat,
                                     has_ball=has_ball, has_hit=has_hit,
                                     has_mob_icon=has_mob_icon, action=action,
                                     helps=helps, element=element,
                                     has_summon=has_summon,
                                     has_keydown=has_keydown,
                                     has_tile=has_tile,
                                     has_affected=has_affected,
                                     has_state=has_state,
                                     skill_type=skill_type,
                                     master_level=master_level)
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
        self.cooldown_totals: Dict[str, float] = {}   # 本次冷却总时长（HUD 遮罩）
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
        """可手动学习的技能（只排除转职附赠被动与 WZ 未声明形态的技能）；给定组则只回该转。"""
        return sorted(
            sid for sid in self.defs
            if sid not in self._passive_ids
            and not self._unsupported(sid)
            and (owner_group is None or sp_group_of_skill(sid) == owner_group))

    def skills_for_group(self, group: int) -> List[str]:
        """技能窗某转页签要展示的全部技能（含自动满级被动，按 id 排序）。

        WZ 未声明施放形态的技能（快速移动等，cast_form=unsupported）不展示，避免空壳。
        """
        return sorted(sid for sid in self.defs
                      if sp_group_of_skill(sid) == group
                      and not self._unsupported(sid))

    def _unsupported(self, skill_id: str) -> bool:
        """该技能是否为 WZ 未声明施放形态（不可施放），用于门控与技能窗过滤。"""
        d = self.defs.get(skill_id)
        return d is not None and cast_form(d, max(1, d.max_level)) == "unsupported"

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
    def can_learn(self, skill_id: str, player_level: int) -> bool:
        """是否此刻可学 / 升 1 级：SP / 前置 req / CharLevel / 未满级全过。

        技能窗「+」按钮显隐与 learn() 共用本判定，杜绝「按钮在、点了没反应」。
        """
        if skill_id in self._passive_ids:
            return False
        if self._unsupported(skill_id):
            return False
        group = sp_group_of_skill(skill_id)
        if self.sp_by_job.get(group, 0) <= 0:
            return False
        d = self.defs.get(skill_id)
        if d is None:
            return False
        cur = self.levels.get(skill_id, 0)
        if cur >= d.max_level:
            return False
        if player_level < d.char_level:
            return False
        for rid, rlv in d.req.items():
            if self._unsupported(rid):
                continue        # 前置未声明施放形态（如快速移动）不阻塞后续技能
            if self.levels.get(rid, 0) < rlv:
                return False
        return True

    def learn(self, skill_id: str, player_level: int) -> bool:
        """消耗该转 1 SP 学习或升级。四重门控见 can_learn（单一事实来源）。

        不自动上快捷键：上键只由玩家主动拖拽触发（assign_skill_to_key）。
        """
        if not self.can_learn(skill_id, player_level):
            return False
        group = sp_group_of_skill(skill_id)
        cur = self.levels.get(skill_id, 0)
        self.sp_by_job[group] -= 1
        self.levels[skill_id] = cur + 1
        return True

    def passive_mods(self) -> Dict[str, int]:
        """已学被动技能的聚合属性修正（跨转累加、确定性）。

        收集两类：转职附赠被动（_passive_ids）与花 SP 学会的被动类型技能。
        被动识别走 core.skill_semantics.is_passive（登记 + skillType + 结构默认），
        逐技能语义映射走 skill_semantics.passive_mods（含 skillType=1 熟练度默认）。
        多数词条各来源求和；crit_mult（暴伤 %）取最强来源（避免多被动互相覆盖）。
        player.total_stats / attack_value / defense_value / crit_rate 等读取本表。
        """
        ids = set(self._passive_ids)
        for sid, lv in self.levels.items():
            d = self.defs.get(sid)
            if lv > 0 and d is not None and skill_semantics.is_passive(d):
                ids.add(sid)
        mods: Dict[str, int] = {}
        for pid in sorted(ids):
            d = self.defs.get(pid)
            lv = self.levels.get(pid, 0)
            if d is None or lv <= 0:
                continue
            for key, value in skill_semantics.passive_mods(d, lv).items():
                if key == "crit_mult":
                    mods[key] = max(mods.get(key, 0), value)
                else:
                    mods[key] = mods.get(key, 0) + value
        return mods

    def combat_procs(self) -> List["skill_spec.Proc"]:
        """已学被动产出的触发式 Proc 子句（终极追击/暴击/必杀），供战斗触发。"""
        out: List["skill_spec.Proc"] = []
        for sid, lv in self.levels.items():
            d = self.defs.get(sid)
            if d is None or lv <= 0 or not skill_semantics.is_passive(d):
                continue
            for e in skill_semantics.effects(d, lv):
                if isinstance(e, skill_spec.Proc):
                    out.append(e)
        return out

    def on_advance(self, jobdef) -> None:
        """转职：附赠 SP 进本职业组池、附赠被动满级（累加进 passive）。不自动上键。"""
        self.add_sp(job_sp_group(jobdef.code), jobdef.advance_sp)
        for p in jobdef.passive_ids:
            pid = str(p)
            self._passive_ids.add(pid)
            d = self.defs.get(pid)
            if d is not None:
                self.levels[pid] = d.max_level

    def inherit(self, old: "SkillBook") -> None:
        """转职累积：把旧技能书的已学等级、各转 SP 结余、被动集合搬进本书。"""
        if old is None:
            return
        self.levels = dict(old.levels)
        self.sp_by_job = dict(old.sp_by_job)
        self._passive_ids = set(old._passive_ids)

    # ── 施放 ───────────────────────────────────────────────────────
    def cast(self, skill_id: str, player_level: int) -> Optional[dict]:
        """校验并返回施放数据（消耗 + 倍率 + 弹道参数 + 效果子句），失败返回 None。

        数据由 SkillSpec 的效果子句驱动（core.skill_semantics 解析），
        同时保留旧字段键以兼容既有战斗/世界/UI 消费方。
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
        spec = d.spec
        form = spec.kind
        if form in ("passive", "unsupported"):
            return None
        effects = spec.effects_at(lv)
        dmg = next((e for e in effects if isinstance(e, skill_spec.Damage)),
                   None)
        buff = next((e for e in effects if isinstance(e, skill_spec.Buff)), None)
        debuff = next((e for e in effects if isinstance(e, skill_spec.Debuff)),
                      None)
        heal = next((e for e in effects if isinstance(e, skill_spec.Heal)), None)
        summon = next((e for e in effects if isinstance(e, skill_spec.Summon)),
                      None)
        field = next((e for e in effects if isinstance(e, skill_spec.Field)),
                     None)
        cleanse = next((e for e in effects if isinstance(e, skill_spec.Cleanse)),
                       None)
        morph = next((e for e in effects if isinstance(e, skill_spec.Morph)),
                     None)
        move = next((e for e in effects if isinstance(e, skill_spec.Move)), None)
        magic = dmg.magic if dmg is not None else False
        data = {
            "id": skill_id,
            "def": d,
            "spec": spec,                        # 分面描述（交付/效果子句）
            "effects": effects,                  # 效果子句列表（新消费方直接读）
            "level": lv,
            # 交付方式（见 skill_spec.DELIVERY_KINDS）
            "form": form,
            "mp_con": d.stat(lv, "mpCon", 0),
            "hp_con": d.stat(lv, "hpCon", 0),
            "damage": dmg.mult if dmg is not None
            else d.stat(lv, "damage", 100) / 100.0,
            "range": d.stat(lv, "range", 0),          # 0 = 默认普攻范围
            "mob_count": dmg.max_targets if dmg is not None
            else d.stat(lv, "mobCount", 1),
            "bullet_count": dmg.shots if dmg is not None
            else max(1, d.stat(lv, "bulletCount", 1)),
            "attack_count": dmg.hits if dmg is not None
            else max(1, d.stat(lv, "attackCount", 1)),
            # WZ 官方冷却字段为 cooltime（秒）；换算成毫秒供 start_cooldown 统一处理
            "cooldown_ms": d.stat(lv, "cooltime", 0) * 1000,
            "repeat": d.repeat,                  # 通道技：按住可连发
            "action": d.action,                  # WZ action：官方施法动作名
            "magic": magic,                      # 魔法伤害走 mdd 与魔法区间
            "element": dmg.element if dmg is not None else d.element,
            "skill_mad": dmg.skill_mad if dmg is not None
            else d.stat(lv, "mad", 0),
            "skill_mastery": dmg.mastery if dmg is not None
            else d.stat(lv, "mastery", 0),
            "drain_pct": dmg.drain_pct if dmg is not None else 0,
            "area": None,                        # WZ lt/rb 矩形（相对 navel）
            "status": None,                      # 对怪状态键（slow/freeze…）
            "freeze": 0.0,                       # 命中冻结秒数（冰冻术）
            "poison_prop": 0,                    # 中毒概率 %（毒雾术）
            "poison_time": 0.0,                  # 中毒持续秒数（毒雾术）
            "slow_x": 0,                          # 减速幅度（% 负值，缓速术）
            "duration": 0.0,                      # debuff / buff 持续秒数
            "heal_pct": 0,                        # 治愈恢复率 %（群体治愈）
        }
        for candidate in (dmg, heal, debuff, field):
            area = getattr(candidate, "area", None)
            if area is not None:
                data["area"] = (tuple(area[0]), tuple(area[1]))
                break
        if debuff is not None and form == "mob_status":
            data["status"] = debuff.status
            data["slow_x"] = debuff.potency           # 兼容旧字段（减速幅度 %）
            data["status_potency"] = debuff.potency   # 状态强度（随状态释义）
            data["status_chance"] = debuff.chance
            data["duration"] = debuff.duration
        if heal is not None:
            data["heal_pct"] = heal.pct     # 恢复率（%），对不死系同作伤害倍率
        if form == "projectile":
            data["projectile"] = True                  # 弹道技：不进近战命中框
            if skill_id in ("10001000", "0001000", "20001000"):
                data["speed"] = settings.SNAIL_THROW_SPEED
                data["life"] = settings.SNAIL_THROW_LIFETIME
            elif magic:
                data["speed"] = settings.MAGIC_BALL_SPEED
                data["life"] = settings.MAGIC_BALL_LIFETIME
        elif magic and form in ("instant", "aoe", "channel"):
            # 无 ball 的魔法攻击（魔法双击/冰冻术/雷电术）：瞬发、无弹道。
            data["cone_attack"] = True
        if dmg is not None and dmg.status is not None:
            status = dmg.status
            # 通用字段：命中附带状态的种类/概率/时长/强度（消费方统一读）
            data["attack_status"] = status.status
            data["attack_status_chance"] = status.chance
            data["attack_status_duration"] = status.duration
            data["attack_status_potency"] = status.potency
            if status.status == "freeze":
                data["freeze"] = status.duration
            elif status.status == "poison":
                data["poison_prop"] = status.chance
                data["poison_time"] = status.duration
        if buff is not None:
            data["buff"] = {"mods": dict(buff.mods), "duration": buff.duration,
                            "party": buff.party}
            data["duration"] = buff.duration
        if summon is not None:
            data["summon"] = {"template": summon.template,
                              "duration": summon.duration,
                              "attack": summon.attack,
                              "interval": summon.interval}
            data["duration"] = summon.duration
        if field is not None:
            data["field"] = {"area": data["area"], "duration": field.duration,
                             "interval": field.interval}
        if cleanse is not None:
            data["cleanse"] = list(cleanse.kinds)
        if morph is not None:
            data["morph"] = {"form": morph.form, "duration": morph.duration}
        if move is not None:
            data["move_mode"] = move.mode
            data["range"] = move.distance
        return data

    def start_cooldown(self, skill_id: str, cooldown_ms: int = 0) -> None:
        """确认出手后写入施放冷却：WZ cooltime（毫秒）优先，缺省看 settings 覆盖表。

        WZ 无 cooltime 的技能（绝大多数攻击技）不写冷却——节奏由攻击动画与
        攻击槽门控决定，而非人工兜底 CD。settings.SKILL_COOLDOWN 可对个别技能
        额外指定冷却（秒）。同时记录总时长，供 HUD 冷却遮罩算比例。
        """
        if cooldown_ms and cooldown_ms > 0:
            seconds = max(1.0, cooldown_ms / 1000.0)
        else:
            seconds = settings.SKILL_COOLDOWN.get(skill_id, 0.0)
            if seconds <= 0:
                return
        self.cooldowns[skill_id] = seconds
        self.cooldown_totals[skill_id] = seconds

    def tick(self, dt: float) -> None:
        for sid in list(self.cooldowns):
            self.cooldowns[sid] -= dt
            if self.cooldowns[sid] <= 0:
                del self.cooldowns[sid]
                self.cooldown_totals.pop(sid, None)

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"sp_by_job": {str(k): v for k, v in self.sp_by_job.items()},
                "levels": dict(self.levels), "passives": sorted(self._passive_ids),
                "hotkeys": {str(k): v for k, v in self.hotkeys.items()}}

    def from_dict(self, data: dict) -> None:
        self.levels = dict(data.get("levels", {}))
        # 附赠被动以当前职业链为准重建（存档的 passives 字段仅历史用途，忽略之）：
        # 新增的附赠被动对旧档生效，被移出附赠集合的技能（如法师 SP 被动）恢复可学。
        self._passive_ids = set()
        for jd in job_chain(self.job):
            for pid in jd.passive_ids:
                pid = str(pid)
                self._passive_ids.add(pid)
                d = self.defs.get(pid)
                if d is not None:
                    self.levels[pid] = d.max_level
        raw_sp = data.get("sp_by_job")
        if raw_sp is not None:
            self.sp_by_job = {int(k): int(v) for k, v in raw_sp.items()}
        else:                                   # 旧档单一 sp → 归入当前职业组
            legacy = int(data.get("sp", 0) or 0)
            self.sp_by_job = {job_sp_group(self.job): legacy} if legacy else {}
        self.hotkeys = {int(k): str(v)
                        for k, v in data.get("hotkeys", {}).items()}
        self.cooldowns.clear()
        self.cooldown_totals.clear()


def assign_skill_to_key(book: SkillBook, bindings, skill_id: str,
                        key: int) -> bool:
    """技能拖到键盘某键上：复用已上槽位或取最小空闲槽，再改绑该槽动作键。

    被占键的让位由 KeyBindings.set 的顶替语义完成（占用者解绑）；未学 / 被动 /
    槽满 / Esc 一律拒绝且不留脏状态。
    """
    d = book.defs.get(skill_id)
    if (skill_id not in book.levels or skill_id not in book.learnable()
            or (d is not None and skill_semantics.is_passive(d))):
        return False
    slot = next((k for k, v in book.hotkeys.items() if v == skill_id), None)
    if slot is None:
        slot = next((k for k in range(1, SKILL_SLOT_COUNT + 1)
                     if k not in book.hotkeys), None)
    if slot is None or not bindings.set(f"skill_{slot}", key):
        return False
    book.hotkeys[slot] = skill_id
    return True
