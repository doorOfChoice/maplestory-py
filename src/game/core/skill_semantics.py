"""技能字段语义层：把 WZ 结构 + level 表翻译成 core.skill_spec 的分面模型。

分两层，避免「点对点」：
1. **结构默认**：由顶层节点（ball/hit/mob/summon/tile/keydown/affected…）与
   level 字段（damage/mad/time/lt-rb/prop…）按固定优先级推导交付方式、目标、
   代价与绝大多数效果子句。
2. **声明式例外表**：只对「同名字段不同义、结构无法判定」的情形登记 ——
   · 触发式被动（终极系/暴击系）
   · 命中附带状态（冰冻/中毒）与对怪状态族（减速/封印…）
   · 解异常/变身/吸血等无结构标记的效果
   例外表是**数据**，不是 per-skill 分支逻辑；新增技能默认命中结构默认。

本模块纯函数、无 WZ/pygame 依赖，可用合成 SkillDef 做单元测试。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from game import settings
from game.core import skill_effects
from game.core.skill_spec import (Area, Buff, Cleanse, Cost, Damage, Debuff,
                                  Effect, Field, Heal, Morph, Move, Proc,
                                  SkillSpec, Summon, TARGET_AREA, TARGET_MULTI,
                                  TARGET_PARTY, TARGET_SELF, TARGET_SINGLE)


# ── 结构默认 ─────────────────────────────────────────────────────────
def _stat(d, level: int, key: str, default: int = 0) -> int:
    """读该级数值：优先 SkillDef.stat()，回退 lv() 表查询（兼容桩对象）。"""
    getter = getattr(d, "stat", None)
    if callable(getter):
        try:
            return int(getter(level, key, default))
        except (TypeError, ValueError):
            return default
    val = d.lv(level).get(key) if hasattr(d, "lv") else None
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _table(d, level: int) -> dict:
    """该级原始数值表（桩对象无 lv() 时返回空表）。"""
    lv = getattr(d, "lv", None)
    return lv(level) if callable(lv) else {}


def _area(d, level: int) -> Optional[Area]:
    table = _table(d, level)
    lt, rb = table.get("lt"), table.get("rb")
    if lt is None or rb is None:
        return None
    return (tuple(lt), tuple(rb))                 # type: ignore[arg-type]


def _offensive(d, level: int) -> bool:
    """该级是否含伤害标记（魔法 mad 或物理 damage）。"""
    return _stat(d, level, "mad", 0) > 0 or _stat(d, level, "damage", 0) > 0


def has_area(d, level: int) -> bool:
    """该级是否带 WZ lt/rb 攻击矩形。"""
    return _area(d, level) is not None


def skill_buff_seconds(d, level: int) -> float:
    """技能若为纯 buff（非攻击）则返回其持续秒数，否则 0.0。

    关键区分：多个攻击技能的 level 表也带 time（冰冻术冻结时长、烈火箭燃烧 DoT、
    引信），若仅凭 time 判定会被误当 buff 吞掉、不触发攻击。故再看 WZ 是否带
    hit 节点（攻击技），或伤害/目标/射程/多发/多段任一 > 0，任一成立即视为攻击技。
    另：带 mob 节点的对怪状态技（击退箭等）无攻击字段但也不是自身 buff，
    持续秒数是状态时长，故一并排除。
    """
    seconds = _stat(d, level, "time", 0) if level > 0 else 0
    if seconds <= 0:
        return 0.0
    if getattr(d, "has_hit", False) or getattr(d, "has_mob_icon", False):
        return 0.0
    if any(_stat(d, level, key, 0) > 0
           for key in ("damage", "mobCount", "range", "bulletCount",
                       "attackCount")):
        return 0.0
    return float(seconds)


def _has(d, flag: str) -> bool:
    return bool(getattr(d, flag, False))


def _has_mp(d) -> bool:
    """WZ level 表任意一级是否消耗 MP（被动/形态技通常不耗）。"""
    levels = getattr(d, "levels", None)
    return any("mpCon" in lvtab for lvtab in levels) if levels else False


def _any_field(d, key: str) -> bool:
    """WZ level 表任意一级是否含某字段。"""
    levels = getattr(d, "levels", None)
    return any(key in lvtab for lvtab in levels) if levels else False


def is_passive(d) -> bool:
    """是否被动技：已登记语义 > skillType 惯例 > 结构默认。

    · 已登记（skill_effects）—— 字段语义已知，最可信。
    · skillType 1/3 —— WZ 明示的熟练度 / 终极追击被动。
    · 结构默认 —— 全程无 mpCon、无任何交付节点（ball/hit/mob/summon/
      keydown/tile/affected）、无 time 持续、无伤害字段，视为被动/utility。
    主动技要么耗 MP，要么有交付节点，要么带持续/伤害，故不会误判。
    """
    if skill_effects.is_passive(d.id):
        return True
    if getattr(d, "skill_type", 0) in (1, 3):
        return True
    if _has_mp(d):
        return False
    if any(_has(d, flag) for flag in
           ("has_ball", "has_hit", "has_mob_icon", "has_summon", "has_keydown",
            "has_tile", "has_affected")):
        return False
    if _any_field(d, "time"):
        return False
    level = max(1, getattr(d, "max_level", 1))
    if _offensive(d, level):
        return False
    return True


# 蜗牛投掷术：同一技能在 0/1/2 转新手树各有一份 id（借怪物贴图发射弹道）
_SNAIL_IDS = {"10001000", "0001000", "20001000"}
# 磁石：把范围内怪物吸向自己（非瞬移，move 的一种特殊模式）
_PULL_SKILLS = {"1121001", "1221001", "1321001"}
# 二段跳（空中再跳一次）与冲刺位移（无 range 字段，需专用执行）
_JUMP_SKILLS = {"4111006", "14101004"}
_DASH_SKILLS = {"11101005", "21001001"}


def delivery(d, level: int) -> str:
    """按 WZ 结构推导交付方式（字符串集合见 skill_spec.DELIVERY_KINDS）。

    优先级刻意保留旧 cast_form 的行为，只在「结构已知更具体」处细化：
    召唤（summon 节点）先于 buff/攻击判定 —— 银鹰召唤/火凤凰同时带 hit，
    旧逻辑会误判成玩家瞬发攻击。
    """
    if level <= 0:
        level = 1
    sid = d.id
    if sid in _SNAIL_IDS:
        return "projectile"
    if is_passive(d):
        return "passive"
    if sid in skill_effects.HEAL_SKILLS:
        return "heal"
    if sid in skill_effects.TELEPORT_SKILLS:
        return "teleport"
    if _has(d, "has_summon"):
        return "summon"
    if _has(d, "has_state"):
        return "buff"                       # 斗气集中等状态技：自增益
    if _has(d, "has_affected") and not _has(d, "has_hit"):
        return "aura"                       # 团队/范围增益（affected 无命中）
    if skill_buff_seconds(d, level) > 0:
        return "buff"
    if _has(d, "has_ball"):
        return "projectile"
    # 多发技无 ball 节点（二连射 3001005：bulletCount=2 但走武器箭矢贴图），
    # 结构上仍是弹道，否则会退化成本体近战瞬发。
    if (_has(d, "has_hit") and not _has(d, "has_ball")
            and _stat(d, level, "bulletCount", 1) > 1):
        return "projectile"
    if _has(d, "has_hit"):
        return "aoe" if has_area(d, level) else "instant"
    if _has(d, "has_mob_icon") and not _offensive(d, level):
        return "mob_status"
    if _has(d, "has_keydown"):
        return "channel"
    if _has(d, "has_tile"):
        return "field"
    if _offensive(d, level):
        return "instant"
    if sid in _JUMP_SKILLS or sid in _DASH_SKILLS:
        return "move"                       # 二段跳 / 冲刺（专用位移）
    if _has_mp(d) and _stat(d, level, "range", 0) > 0:
        return "move"                       # 带位移距离的位移技（快速移动变体）
    return "unsupported"


def targeting(d, level: int) -> str:
    """目标选择：团体 > 范围 > 多体 > 单体/自身。"""
    if _has(d, "has_affected"):
        return TARGET_PARTY
    if has_area(d, level):
        return TARGET_AREA
    if _stat(d, level, "mobCount", 1) > 1:
        return TARGET_MULTI
    kind = delivery(d, level)
    if kind in ("buff", "move", "heal"):
        return TARGET_SELF
    return TARGET_SINGLE if kind in ("projectile", "instant", "aoe") \
        else TARGET_SELF


def cost(d, level: int) -> Cost:
    """施放代价（level 表字段）。"""
    table = _table(d, level)
    item_id = table.get("itemCon")
    mesos = table.get("moneyCon")
    return Cost(
        mp=_stat(d, level, "mpCon", 0),
        hp=_stat(d, level, "hpCon", 0),
        item_id="" if item_id is None else str(item_id),
        item_count=_stat(d, level, "itemConNo", 0) if item_id is not None else 0,
        mesos=int(mesos) if isinstance(mesos, (int, str)) and str(mesos).isdigit()
        else 0,
        cooldown=float(_stat(d, level, "cooltime", 0)),
    )


# ── 声明式例外表（数据，非分支逻辑）──────────────────────────────────
# 暴击系被动：WZ 用 prop=发动率、damage=附加伤害。含强力箭/贯穿箭等族。
_CRIT_PASSIVES = {
    "3000001", "3110001",          # 强力箭 / 贯穿箭（弓）
    "13000000", "15110000",        # 强力箭 / 必杀拳
    "4100001", "14100001",         # 强力投掷
    "5110000",                     # 迷惑攻击
    "3210001",                     # 贯穿箭（弩）
}
# 贯穿类：额外有 x=目标 HP% 阈值、y=必杀几率（必杀 Proc）。
_DEADLY_PASSIVES = {"3110001", "3210001"}

# 命中附带状态（伤害型攻击）：技能 id → 状态键。持续/概率取 level 的 time/prop。
_ATTACK_STATUS = skill_effects.ATTACK_STATUS

# 无伤害的对怪状态：技能 id → 状态键。强度取 x。
_DEBUFF_SKILLS = skill_effects.DEBUFF_SKILLS
# 无结构标记、但语义为对怪减速的 4 转击退箭等（mob 节点 + time，无伤害）。
_DEBUFF_EXTRA = {
    "3121007": "slow",   # 击退箭（牵制射击）
    "3221006": "slow",   # 刺眼箭
    "2111004": "seal",   # 封印术
    "2211004": "seal",
    "12111002": "seal",
    "4111003": "slow",   # 影网术
    "14111001": "slow",
    "2311005": "curse",  # 巫毒术
    "4001002": "curse",  # 诅咒术
    "14001002": "curse",
    "1201006": "attack_down",   # 压制术
    "1111007": "def_down",      # 防御崩坏
}

# 解异常：勇士的意志系列（解除诱惑）。
_CLEANSE_SKILLS = {
    "1121010", "2121008", "2221008", "2321002", "3121009",
    "3221008", "4121010", "4221008", "5121010", "5221010",
}
# 吸血：造成伤害的 x% 回血（WZ 无统一结构标记）。
_DRAIN_SKILLS = {"4101005": "x", "4211004": "x", "4111005": "x"}

# 伤害型攻击附带的控制状态：hit + mob 节点，WZ 只给 prop/time 不表达种类。
# 命中后按 prop% 施加对应状态（stun 等），执行端走 Monster.apply_status。
_ATTACK_CONTROL = {
    "3101003": "stun", "3201003": "stun",       # 强弓 / 强弩
    "3101005": "stun",                           # 爆炸箭
    "4211002": "stun", "5201004": "stun", "4121008": "stun",   # 落叶斩/迷惑射击/忍者冲击
    "1111008": "stun",                           # 虎咆哮
    "1211002": "stun",                           # 属性攻击
}


def _proc_effects(d, level: int, st: Optional[int]) -> Tuple[Proc, ...]:
    """触发式被动 → Proc 子句（终极追击/暴击/必杀）。"""
    sid = d.id
    procs = []
    if st == 3 or sid in _CRIT_PASSIVES:
        chance = _stat(d, level, "prop", 0)
        mult = _stat(d, level, "damage", 0) / 100.0
        if chance > 0:
            procs.append(Proc("final_attack" if st == 3 else "critical",
                              chance=chance, mult=mult))
    if sid in _DEADLY_PASSIVES:
        threshold = _stat(d, level, "x", 0)
        chance = _stat(d, level, "y", 0)
        if threshold > 0 and chance > 0:
            procs.append(Proc("deadly", chance=chance, mult=1.0,
                              threshold=threshold))
    return tuple(procs)


def _attack_status(sid: str, d, level: int, area: Optional[Area],
                   max_targets: int) -> Optional[Debuff]:
    """伤害型攻击命中后附带的状态（冰冻/中毒/眩晕…）。"""
    kind = _ATTACK_STATUS.get(sid) or _ATTACK_CONTROL.get(sid)
    if kind is None:
        return None
    duration = float(_stat(d, level, "time", 0))
    if kind == "freeze":
        return Debuff("freeze", chance=100, duration=duration,
                      area=area, max_targets=max_targets)
    if kind == "poison":
        return Debuff("poison", chance=_stat(d, level, "prop", 0),
                      duration=duration, potency=level,
                      area=area, max_targets=max_targets)
    # 控制类（眩晕等）WZ 常只有 prop、无 time：给一个默认时长
    if duration <= 0:
        duration = settings.ATTACK_STATUS_DEFAULT_DURATION
    return Debuff(kind, chance=_stat(d, level, "prop", 0),
                  duration=duration, area=area, max_targets=max_targets)


def effects(d, level: int) -> Tuple[Effect, ...]:
    """按结构默认 + 例外表解析该级的全部效果子句（正交，可同时存在多个）。"""
    if level <= 0:
        level = 1
    sid = d.id
    kind = delivery(d, level)
    area = _area(d, level)
    mob_count = max(1, _stat(d, level, "mobCount", 1))
    out: list = []

    # 被动：只产出触发式子句（终极追击/暴击/必杀）；属性增益走 passive_mods 聚合
    if kind == "passive":
        return _proc_effects(d, level, getattr(d, "skill_type", None))

    # 召唤
    if _has(d, "has_summon"):
        out.append(Summon(
            template=sid,
            duration=float(_stat(d, level, "time", 0)),
            attack=_stat(d, level, "pad", 0),
            interval=settings.SUMMON_ATTACK_INTERVAL,
        ))

    # 地面/持续区域（与攻击共存：如火牢、毒雾；区域本身按间隔结算）
    if _has(d, "has_tile"):
        out.append(Field(area=area,
                         duration=float(_stat(d, level, "time", 0)),
                         interval=settings.FIELD_TICK_INTERVAL))

    # 治疗
    if kind == "heal":
        out.append(Heal(pct=_stat(d, level, "hp", 0), area=area))

    # 位移（teleport 瞬移 / move 位移；磁石拉怪、二段跳、冲刺各为一种模式）
    if kind in ("teleport", "move"):
        if sid in _JUMP_SKILLS:
            out.append(Move(distance=0, mode="jump"))
        elif sid in _DASH_SKILLS:
            out.append(Move(distance=_stat(d, level, "range", 0) or 120,
                            mode="dash"))
        else:
            mode = "teleport" if kind == "teleport" else (
                "pull" if sid in _PULL_SKILLS else "dash")
            out.append(Move(distance=_stat(d, level, "range", 0), mode=mode))

    # 纯增益 / 团体增益：只要有持续就产出子句（mods 可为空，表示效果未实装，
    # 但仍算施放成功、不落入攻击流程）
    if kind in ("buff", "aura"):
        stat = lambda key, d=d, lv=level: _stat(d, lv, key, 0)   # noqa: E731
        mods = skill_effects.buff_mods(sid, stat)
        duration = float(_stat(d, level, "time", 0))
        if duration > 0:
            out.append(Buff(mods=mods, duration=duration,
                            party=kind == "aura", area=area))

    # 对怪无伤害状态
    status_key = _DEBUFF_SKILLS.get(sid) or _DEBUFF_EXTRA.get(sid)
    if status_key is not None and not _offensive(d, level):
        out.append(Debuff(status_key, chance=_stat(d, level, "prop", 100),
                          duration=float(_stat(d, level, "time", 0)),
                          potency=_stat(d, level, "x", 0),
                          area=area, max_targets=mob_count))

    # 伤害（攻击形态）：弹道/瞬发/AOE/引导/地面攻击
    if kind in ("projectile", "instant", "aoe", "channel", "field"):
        magic = _stat(d, level, "mad", 0) > 0
        element = str(getattr(d, "element", "") or "")
        st = getattr(d, "skill_type", None)
        status = _attack_status(sid, d, level, area, mob_count)
        drain = 0
        if sid in _DRAIN_SKILLS:
            drain = _stat(d, level, _DRAIN_SKILLS[sid], 0)
        out.append(Damage(
            mult=1.0 if magic else _stat(d, level, "damage", 100) / 100.0,
            hits=max(1, _stat(d, level, "attackCount", 1)),
            shots=max(1, _stat(d, level, "bulletCount", 1)),
            max_targets=mob_count,
            area=area, element=element, magic=magic,
            skill_mad=_stat(d, level, "mad", 0),
            mastery=_stat(d, level, "mastery", 0),
            drain_pct=drain,
            status=status,
            procs=_proc_effects(d, level, st),
        ))

    # 解异常 / 变身
    if sid in _CLEANSE_SKILLS:
        out.append(Cleanse(("seduce",)))
    morph = _table(d, level).get("morph")
    if morph is not None and str(morph).isdigit() and int(morph) > 0:
        out.append(Morph(form=str(morph),
                         duration=float(_stat(d, level, "time", 0))))

    return tuple(out)


def passive_mods(d, level: int) -> Dict[str, int]:
    """被动技能 → 属性词条（登记语义 > skillType 惯例 > 通用回退）。

    · 已登记（skill_effects）—— 逐技能字段语义。
    · skillType=1（熟练度）—— 结构默认 mastery + x(命中)，覆盖未登记职业的
      「精准XX」被动。
    · skillType=3（终极追击）—— 不产属性词条，触发效果由 Proc 子句承载。
    · 其余 —— 通用回退（pad→atk 等平坦字段），不硬套 x/y/prop/damage。
    """
    sid = d.id
    if not skill_effects.is_passive(sid) and getattr(d, "skill_type", 0) == 1:
        mods: Dict[str, int] = {}
        mastery = _stat(d, level, "mastery", 0)
        acc = _stat(d, level, "x", 0)
        if mastery:
            mods["mastery"] = mastery
        if acc:
            mods["acc"] = acc
        return mods
    stat = lambda key, d=d, lv=level: _stat(d, lv, key, 0)   # noqa: E731
    return skill_effects.passive_mods(sid, stat)


def build_spec(d) -> SkillSpec:
    """由 SkillDef（鸭子类型？字段齐全）构造不可变 SkillSpec。"""
    level = max(1, d.max_level)
    return SkillSpec(
        id=d.id, name=d.name, desc=d.desc,
        max_level=d.max_level,
        master_level=int(getattr(d, "master_level", 0) or 0),
        kind=delivery(d, level),
        targeting=targeting(d, level),
        element=str(getattr(d, "element", "") or ""),
        action=str(getattr(d, "action", "") or ""),
        invisible=bool(getattr(d, "invisible", False)),
        repeat=bool(getattr(d, "repeat", False)),
        req=dict(getattr(d, "req", {}) or {}),
        char_level=int(getattr(d, "char_level", 0) or 0),
        cost=lambda lv, d=d: cost(d, lv),
        effects=lambda lv, d=d: effects(d, lv),
    )
