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
  施放形态（弹道/瞬发/AOE/buff/怪状态）由 WZ 顶层节点结构推导（见 cast_form），
  只有字段语义（x/y 含义、状态种类）留给 core.skill_effects 的逐技能表。
  被动/buff 的 WZ 字段语义差异由 core.skill_effects 统一翻译（见该模块）。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from game import settings
from game.core import skill_effects
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
                 element: str = ""):
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
    """技能若为纯 buff（非攻击）则返回其持续秒数，否则 0.0。

    关键区分：多个攻击技能的 level 表也带 time（冰冻术冻结时长、烈火箭燃烧 DoT、
    引信），若仅凭 time 判定会被误当 buff 吞掉、不触发攻击。故再看 WZ 是否带
    hit 节点（攻击技），或 damage/mobCount/range/bulletCount/attackCount 任一
    > 0，任一成立即视为攻击技能。
    """
    seconds = d.stat(level, "time", 0) if level > 0 else 0
    if seconds <= 0:
        return 0.0
    if getattr(d, "has_hit", False):
        return 0.0
    if any(d.stat(level, key, 0) > 0
           for key in ("damage", "mobCount", "range", "bulletCount",
                       "attackCount")):
        return 0.0
    return float(seconds)


def _offensive(d: "SkillDef", level: int) -> bool:
    """该级数值表是否含伤害标记（魔法 mad 或物理 damage）。"""
    return d.stat(level, "mad", 0) > 0 or d.stat(level, "damage", 0) > 0


def _has_area(d: "SkillDef", level: int) -> bool:
    """该级数值表是否带 WZ lt/rb 攻击矩形。"""
    table = d.lv(level)
    return table.get("lt") is not None and table.get("rb") is not None


def cast_form(d: "SkillDef", level: int) -> str:
    """按 WZ 结构推导技能的施放形态（不再散落技能 id 硬编码）。

    判定优先级由「WZ 顶层节点 + level 字段」共同决定：
    · passive    —— 已登记被动（skill_effects 语义表，结构无法判定），不可落键
    · heal       —— 已登记治愈技（群体治愈），回血 + 对不死系伤害，非普通攻击
    · teleport   —— 已登记瞬移技（快速移动），按方向键位移，非攻击
    · buff       —— 有 time 且无攻击属性（魔法盾/精神力/无形箭…），扣消耗直接上 buff
    · projectile —— 有 ball 节点（魔法弹/火焰箭/圣箭术…），生成弹道
    · instant    —— 有 hit 或带伤害标记（魔法双击/冰冻术/武器攻击），瞬发命中
    · aoe        —— instant 且带 lt/rb（雷电术/箭雨），按自身矩形结算
    · mob_status —— 有 mob 节点且无伤害（缓速术/击退箭），对怪上状态无伤害
    · unsupported—— 无任何施放标记（仅有 range/time 等无法独立成形的字段），暂不可施放
    """
    if level <= 0:
        level = 1
    sid = d.id
    if sid == settings.SNAIL_THROW_SKILL_ID:
        return "projectile"                     # 蜗牛投掷：借怪物贴图发射弹道
    if skill_effects.is_passive(sid):
        return "passive"
    if sid in skill_effects.HEAL_SKILLS:
        return "heal"
    if sid in skill_effects.TELEPORT_SKILLS:
        return "teleport"
    if skill_buff_seconds(d, level) > 0:
        return "buff"
    if d.has_ball:
        return "projectile"
    if d.has_hit:
        return "aoe" if _has_area(d, level) else "instant"
    if d.has_mob_icon and not _offensive(d, level):
        return "mob_status"
    if _offensive(d, level):
        return "instant"
    return "unsupported"


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
                                     helps=helps, element=element)
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

        收集两类：转职附赠被动（_passive_ids）与花 SP 学会的被动类型技能
        （skill_effects.is_passive）。逐技能语义映射见 core/skill_effects。
        多数词条各来源求和；crit_mult（暴伤 %）取最强来源（避免多被动互相覆盖）。
        player.total_stats / attack_value / defense_value / crit_rate 等读取本表。
        """
        ids = set(self._passive_ids)
        ids.update(sid for sid in self.levels if skill_effects.is_passive(sid))
        mods: Dict[str, int] = {}
        for pid in sorted(ids):
            d = self.defs.get(pid)
            lv = self.levels.get(pid, 0)
            if d is None or lv <= 0:
                continue
            stat = lambda key, d=d, lv=lv: d.stat(lv, key, 0)
            for key, value in skill_effects.passive_mods(pid, stat).items():
                if key == "crit_mult":
                    mods[key] = max(mods.get(key, 0), value)
                else:
                    mods[key] = mods.get(key, 0) + value
        return mods

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
        form = cast_form(d, lv)
        if form in ("passive", "unsupported"):
            return None
        # 魔法攻击技：该级有 mad 加成且形态为攻击/弹道（buff 的 time 是持续、
        # mob_status 的 time 是状态时长，均不参与魔法区间）。
        # 这类技能 WZ 无 damage 倍率，伤害由玩家魔法区间（含 skill_mad/mastery）决定。
        magic = (form in ("projectile", "instant", "aoe")
                 and d.stat(lv, "mad", 0) > 0)
        data = {
            "id": skill_id,
            "def": d,
            "level": lv,
            # 施放形态：由 WZ 顶层节点推导（见 cast_form），供战斗/世界分派
            "form": form,                        # buff/projectile/instant/aoe/mob_status
            "mp_con": d.stat(lv, "mpCon", 0),
            "hp_con": d.stat(lv, "hpCon", 0),
            "damage": d.stat(lv, "damage", 100) / 100.0,
            "range": d.stat(lv, "range", 0),          # 0 = 默认普攻范围
            "mob_count": d.stat(lv, "mobCount", 1),
            "bullet_count": max(1, d.stat(lv, "bulletCount", 1)),
            "attack_count": max(1, d.stat(lv, "attackCount", 1)),
            # WZ 官方冷却字段为 cooltime（秒）；换算成毫秒供 start_cooldown 统一处理
            "cooldown_ms": d.stat(lv, "cooltime", 0) * 1000,
            "repeat": d.repeat,                  # 通道技：按住可连发
            "action": d.action,                  # WZ action：官方施法动作名
            "magic": magic,                      # 魔法伤害走 mdd 与魔法区间
            "element": d.element,                # WZ elemAttr：属性克制元素字母
            "skill_mad": d.stat(lv, "mad", 0),
            "skill_mastery": d.stat(lv, "mastery", 0),
            # WZ lt/rb 矩形（相对 navel）：AOE 自身范围 / mob_status debuff 范围
            "area": None,
            "status": None,                      # mob_status 的状态键（slow/freeze…）
            "freeze": 0.0,                       # 命中冻结秒数（冰冻术）
            "poison_prop": 0,                    # 中毒概率 %（毒雾术）
            "poison_time": 0.0,                  # 中毒持续秒数（毒雾术）
            "slow_x": 0,                          # 减速幅度（% 负值，缓速术）
            "duration": 0.0,                      # debuff 持续秒数
            "heal_pct": 0,                        # 治愈恢复率 %（群体治愈）
        }
        if form in ("aoe", "mob_status", "heal") and _has_area(d, lv):
            data["area"] = (tuple(d.lv(lv)["lt"]), tuple(d.lv(lv)["rb"]))
        if form == "mob_status":
            data["status"] = skill_effects.DEBUFF_SKILLS.get(skill_id)
            data["slow_x"] = d.stat(lv, "x", 0)
            data["duration"] = float(d.stat(lv, "time", 0))
        elif form == "heal":
            data["heal_pct"] = d.stat(lv, "hp", 0)     # 恢复率（%），对不死系同作伤害倍率
        elif form == "teleport":
            pass                                        # range 已在通用字段（瞬移距离）
        elif form == "projectile":
            data["projectile"] = True                  # 弹道技：不进近战命中框
            if skill_id == settings.SNAIL_THROW_SKILL_ID:
                data["speed"] = settings.SNAIL_THROW_SPEED
                data["life"] = settings.SNAIL_THROW_LIFETIME
            elif magic:
                data["speed"] = settings.MAGIC_BALL_SPEED
                data["life"] = settings.MAGIC_BALL_LIFETIME
        elif magic:
            # 无 ball 的魔法攻击（魔法双击/冰冻术/雷电术）：瞬发、无弹道。
            # WZ 带 lt/rb 的按角色周围矩形结算（雷电术自身 AOE），否则命中瞄准扇形。
            data["cone_attack"] = True
        if form in ("instant", "aoe", "projectile"):
            status = skill_effects.ATTACK_STATUS.get(skill_id)
            if status == "freeze":
                data["freeze"] = float(d.stat(lv, "time", 0))
            elif status == "poison":
                data["poison_prop"] = d.stat(lv, "prop", 0)
                data["poison_time"] = float(d.stat(lv, "time", 0))
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
    if (skill_id not in book.levels or skill_id not in book.learnable()
            or skill_effects.is_passive(skill_id)):
        return False
    slot = next((k for k, v in book.hotkeys.items() if v == skill_id), None)
    if slot is None:
        slot = next((k for k in range(1, SKILL_SLOT_COUNT + 1)
                     if k not in book.hotkeys), None)
    if slot is None or not bindings.set(f"skill_{slot}", key):
        return False
    book.hotkeys[slot] = skill_id
    return True
