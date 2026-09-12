"""技能字段语义映射：WZ level 表字段 → buff / 被动 mod 词条（纯函数，无 WZ 依赖）。

WZ 的 level 表字段语义随技能而异，无法用一张表覆盖全部：
· 主动 buff：多数用固定字段（pad/mad/pdd/mdd/acc/eva/speed/jump/hp/mp/四维），
  少数用 x/y 表意（楓葉祝福的全属性%、會心之眼的暴击率/暴伤），逐技能覆盖。
· 被动：字段含义更杂（x/y/prop/damage/mastery/range 各技能不同），
  采用逐技能声明；未登记的被动回退通用字段（pad→atk 等），绝不硬套 prop/damage。

词条约定（与 core.consumables 的特效药百分比键区分，避免命名冲突）：
· 平坦加值：str/dex/int/luk、hp/mp、atk(物攻)、matk(魔攻)、def(物防)、
  mdef(魔防)、acc(命中)、eva(回避)、range(射程 px)。
· buff 的平坦命中/回避用 acc_flat/eva_flat：特效药已占用 acc/eva 表百分比。
· 百分比：speed/jump（面板移速/跳跃）、crit（暴击率）、crit_mult（暴伤）、
  stat_pct（四维全属性）、mastery（熟练度百分点）、dmg_reduce（物理伤害减免%）。
· mp_regen：MP 自然回复加成（单位 0.1/s，玩家 mp_regen() 换算）。
"""

from __future__ import annotations

from typing import Callable, Dict

# stat 取值回调：输入 WZ 字段名，返回该级整数值（不存在返回 0）。
StatFn = Callable[[str], int]

# ── 主动 buff 通用字段（mod 键 → WZ 字段）────────────────────────────
_BUFF_FIELDS: Dict[str, str] = {
    "atk": "pad", "matk": "mad", "def": "pdd", "mdef": "mdd",
    "acc_flat": "acc", "eva_flat": "eva",
    "speed": "speed", "jump": "jump",
    "hp": "hp", "mp": "mp",
    "str": "str", "dex": "dex", "int": "int", "luk": "luk",
}

# 主动 buff 逐技能覆盖（mod 键 → WZ 字段）。登记后 **仅** 使用本表，
# 不再套通用字段——避免把召唤物的 pad / 未实装技能的错误字段当玩家增益。
_BUFF_OVERRIDES: Dict[str, Dict[str, str]] = {
    # 已实装效果
    "3121000": {"stat_pct": "x"},                 # 楓葉祝福：全属性 +x%
    "3121002": {"crit": "x", "crit_mult": "y"},   # 會心之眼：暴击率/暴伤
    # 未实装（显式置空，避免错误字段生效）
    "3101002": {},   # 快速之弓：x=攻速阶段
    "3101004": {},   # 無形之箭：箭矢不消耗
    "3111002": {},   # 替身術：召唤
    "3111005": {},   # 銀鷹召喚：pad 为召唤物攻击，非玩家增益
    "3121006": {},   # 召喚鳳凰：pad 为召唤物攻击，非玩家增益
    "3121007": {},   # 牽制射擊：debuff 技，非自身 buff
    "2001002": {"magic_guard": "x"},   # 魔法盾：x=伤害转 MP 比例
    "2301003": {"dmg_reduce": "x"},    # 神之保护：x=物理伤害减免 %（仅物理）
    # 魔法铠甲(2001003) 走通用字段 pdd→def，无需覆盖
}

# ── 攻击附带的怪物状态 ───────────────────────────────────────────────
# 伤害型攻击命中后施加的状态：技能 id → 状态键（持续秒数取 level 的 time）。
ATTACK_STATUS: Dict[str, str] = {
    "2201004": "freeze",   # 冰冻术：命中冻结 time 秒
    "2101005": "poison",   # 毒雾术：prop% 概率中毒 time 秒
}

# 怪物 debuff 技：技能 id → 状态键。施放形态由 WZ 的 mob 节点推导（见 skills.cast_form），
# 本表只负责「哪一种状态」这一 WZ 无法表达的语义。不进入伤害结算，
# 按 lt/rb 范围选最多 mobCount 只目标施加（减速幅度取 level 的 x，负=减速）。
DEBUFF_SKILLS: Dict[str, str] = {
    "2101003": "slow",     # 缓速术（火毒）
    "2201003": "slow",     # 缓速术（冰雷）
}

# 群体治愈：WZ 有 hit 节点但无伤害字段，靠 hp（恢复率%）与 undead 标记决定效果，
# 形态与常规 AOE 不同，单独登记（见 combat._cast_heal）。
HEAL_SKILLS = {"2301002"}

# 快速移动（瞬移）：WZ 仅有 range/mpCon，靠方向键瞬移一段距离，形态需专用输入。
TELEPORT_SKILLS = {"2101002", "2201002", "2301001"}


# ── 被动逐技能声明（mod 键 → WZ 字段）────────────────────────────────
_PASSIVE_FIELDS: Dict[str, Dict[str, str]] = {
    "3000000": {"acc": "x"},                      # 精準強化：x=命中
    "3000001": {"crit": "prop", "crit_mult": "damage"},   # 霸王箭
    "3000002": {"range": "range"},                # 百步穿楊：射程
    "3100000": {"mastery": "mastery", "acc": "x"},        # 精準之弓
    "3100001": {},                                # 終極之弓：触发式追击，未实现
    "3110000": {"speed": "speed"},                # 疾風步
    "3110001": {"crit": "prop", "crit_mult": "damage"},   # 致命箭
    "3120005": {"mastery": "mastery", "acc": "x"},        # 弓術精通
    "2000001": {"mp": "x"},                       # 魔力强化：x=MaxMP 提升
    "2000000": {"mp_regen": "mp_regen"},          # 魔力恢复：合成表（WZ 无数值），提升自然回蓝
    "2100000": {},                                # 魔力吸收（火毒）：命中吸怪 MP，combat._absorb_mp
    "2200000": {},                                # 魔力吸收（冰雷）：同上
    "2300000": {},                                # 魔力吸收（牧师）：同上
}

# 未登记被动的通用回退字段（平坦键，不使用 x/y/prop/damage 等歧义字段）
_PASSIVE_FALLBACK: Dict[str, str] = {
    "atk": "pad", "matk": "mad", "def": "pdd", "mdef": "mdd",
    "acc": "acc", "eva": "eva",
    "speed": "speed", "jump": "jump",
    "hp": "hp", "mp": "mp",
    "str": "str", "dex": "dex", "int": "int", "luk": "luk",
}


def _collect(fields: Dict[str, str], stat: StatFn) -> Dict[str, int]:
    mods: Dict[str, int] = {}
    for mod_key, wz_field in fields.items():
        value = stat(wz_field)
        if value:
            mods[mod_key] = mods.get(mod_key, 0) + value
    return mods


def buff_mods(skill_id: str, stat: StatFn) -> Dict[str, int]:
    """主动 buff 技能 → 平坦 mod 词条。

    已登记覆盖的技能只用覆盖表（可为空 = 未实装/无玩家增益）；
    其余走通用字段表。
    """
    fields = _BUFF_OVERRIDES.get(str(skill_id), _BUFF_FIELDS)
    return _collect(fields, stat)


def passive_mods(skill_id: str, stat: StatFn) -> Dict[str, int]:
    """被动技能 → mod 词条（已登记走逐技能声明，未知走通用回退）。"""
    fields = _PASSIVE_FIELDS.get(str(skill_id), _PASSIVE_FALLBACK)
    return _collect(fields, stat)


def is_passive(skill_id: str) -> bool:
    """技能是否为被动类型（已登记被动语义）：效果计入 passive_mods、不可落键施放。"""
    return str(skill_id) in _PASSIVE_FIELDS
