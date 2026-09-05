"""数值系统：四维属性、加点、HP/MP 成长、攻防与伤害结算、穿戴门控、经验查表。

设计哲学：全部为纯函数（输入 dict/int，输出新值），不触碰 WZ 与 pygame，
单测用合成数据即可覆盖。玩家侧（player.py）只负责持有状态并调用这里。

伤害公式（AyumiLove 经典物理向，非官方 v113 全量还原，但贴近物理系手感）：
    面板攻击力 = (主属性×主倍率 + 副属性) × 武器攻击力 / 100
    弓/弩：主 DEX×2.5、副 STR；其余近战：主 STR×4.0、副 DEX。
    实际伤害 = 面板 × 技能倍率 × rand(Min~Max)（Min≈Max×mastery）
    怪物减免 = 等级差 D=max(0, mobLevel-playerLevel) 时：
        MAX走 (1-0.01D) − mobPDD×0.5；MIN 走 (1-0.01D) − mobPDD×0.6
    暴击率(%) 判定命中则 ×crit_mult。

经验需求：非指数曲线，改用官方 v113 的逐级经验表（见 EXP_TO_NEXT）。
"""

from __future__ import annotations

import random
from typing import Dict, Mapping, Optional, Tuple

from game import settings

STAT_KEYS = ("str", "dex", "int", "luk")
STAT_LABELS = {"str": "力量", "dex": "敏捷", "int": "智力", "luk": "幸运"}

# ── 武器属性权重（主属性×W + 副属性）/100 × 武器攻击力 ──────────────────
MAIN_W_RANGED = 2.5    # 弓/弩：主 DEX×2.5
MAIN_W_MELEE = 4.0     # 近战：主 STR×4.0（战士/拳，简化）
SUB_STR = 1.0          # 副属性直接计入

# 默认熟练度（Min 的下限百分比）：0.9 = 伤害下限约为上限的 90%
DEFAULT_MASTERY = 0.9

# ── 经验查表（官方 v113 BigBang 逐级「升到下一级所需 EXP」）──────────────
# 数值取自 MapleStoryWiki Experience/Leveling Tables（v113 世代）。
# 该表为真实逐级数值，非推导曲线；<1 或 >len 用边界兜底（见 exp_to_next）。
EXP_TO_NEXT: Dict[int, int] = {
    1: 15, 2: 34, 3: 57, 4: 92, 5: 135, 6: 372, 7: 560, 8: 840, 9: 1242,
    10: 1242, 11: 1242, 12: 1242, 13: 1242, 14: 1242,
    15: 1490, 16: 1788, 17: 2145, 18: 2574, 19: 3088,
    20: 3705, 21: 4446, 22: 5335, 23: 6402, 24: 7682, 25: 9218,
    26: 11062, 27: 13274, 28: 15929, 29: 19112,
    30: 19112, 31: 19112, 32: 19112, 33: 19112, 34: 19112,
    35: 22934, 36: 27520, 37: 33024, 38: 39628, 39: 47553, 40: 51357,
    41: 55465, 42: 59902, 43: 64694, 44: 69869, 45: 75458, 46: 81494,
    47: 88013, 48: 95054, 49: 102658, 50: 110870,
    51: 119739, 52: 129318, 53: 139663, 54: 150836, 55: 162902,
    56: 175934, 57: 190008, 58: 205208, 59: 221624, 60: 221624,
}

# 超过 EXP_TO_NEXT 表上界后的每级增长倍率（文档为 +6.5%/级）
EXP_TAIL_GROWTH = 1.065


def base_stats() -> Dict[str, int]:
    """新角色的初始四维。"""
    return dict(settings.BASE_STATS)


def allocate(stats: Mapping[str, int], ap: int, stat: str,
             n: int = 1) -> Tuple[Dict[str, int], int]:
    """手动加点：属性 +n、AP −n；AP 不足或属性名非法则原样返回。"""
    if stat not in STAT_KEYS or n < 1 or ap < n:
        return dict(stats), ap
    new = dict(stats)
    new[stat] += n
    return new, ap - n


def auto_allocate(stats: Mapping[str, int], ap: int,
                  weights: Mapping[str, int]) -> Tuple[Dict[str, int], int]:
    """一键自动分配：按职业权重轮转把 AP 全部投完。"""
    new = dict(stats)
    order = [(k, w) for k, w in weights.items() if k in STAT_KEYS and w > 0]
    if not order or ap <= 0:
        return new, max(0, ap)
    # 轮转展开：每轮按权重给各属性 +1，直到 AP 用完
    while ap > 0:
        for key, _w in order:
            if ap <= 0:
                break
            new[key] += 1
            ap -= 1
    return new, 0


def max_hp(level: int, hp_gain: int, equip_hp: int) -> int:
    return settings.HP_BASE + level * hp_gain + equip_hp


def max_mp(level: int, mp_gain: int, equip_mp: int) -> int:
    return settings.MP_BASE + level * mp_gain + equip_mp


def attack(stats: Mapping[str, int], pad: int, ranged: bool) -> int:
    """面板攻击力（上限端）：(主属性×主倍率 + 副属性) × 武器攻击力 / 100。"""
    lo, hi = attack_range(stats, pad, ranged)
    return hi


def attack_range(stats: Mapping[str, int], pad: int, ranged: bool,
                 mastery: float = DEFAULT_MASTERY) -> Tuple[int, int]:
    """物理攻击区间 (min, max)（武器伤害上限前、未受怪防/技能倍率影响）。

    Min = (主×主倍率×mastery + 副)×pad/100；Max = (主×主倍率 + 副)×pad/100。
    """
    if ranged:
        main = stats["dex"] * MAIN_W_RANGED
        sub = stats["str"] * SUB_STR
    else:
        main = stats["str"] * MAIN_W_MELEE
        sub = stats["dex"] * SUB_STR
    hi = int((main + sub) * pad / 100.0)
    lo = int((main * mastery + sub) * pad / 100.0)
    return max(1, lo), max(1, hi)


def roll_damage(atk_lo: int, atk_hi: int, mult: float, mob_pd: int,
                player_level: int, mob_level: int,
                rng: random.Random, crit_rate: float = 0.0,
                crit_mult: float = settings.CRIT_MULT) -> Tuple[int, bool]:
    """单次命中伤害（AyumiLove 经典物理公式）。

    :param atk_lo / atk_hi: 面板攻击区间（attack_range 的返回值）。
    :param mult: 技能伤害倍率（普攻 1.0）。
    :param mob_pd: 怪物物理防御（weaponDefense）。
    :param player_level / mob_level: 用于等级差减免 D=max(0, mob-player)。
    :param rng: 注入的随机数发生器（可复现）。
    :param crit_rate: 暴击率（%）。
    :param crit_mult: 暴击伤害倍率（默认 settings.CRIT_MULT，被霸王箭等覆盖）。
    :return: (实际伤害, 是否暴击)；伤害下限 1。
    """
    d = max(0, mob_level - player_level)
    mult_fall = max(0.0, 1.0 - 0.01 * d)
    hi = atk_hi * mult * mult_fall - mob_pd * 0.5
    lo = atk_lo * mult * mult_fall - mob_pd * 0.6
    raw = rng.uniform(min(lo, hi), max(lo, hi))
    dmg = max(1, int(raw))
    crit = crit_rate > 0 and rng.random() * 100.0 < crit_rate
    if crit:
        dmg = max(1, int(dmg * crit_mult))
    return dmg, crit


def defense(stats: Mapping[str, int], equip_pdd: int) -> int:
    """防御力：装备 PDD 总和 + DEX//10。"""
    return equip_pdd + stats["dex"] // 10


def exp_to_next(level: int) -> int:
    """升到下一级所需经验（官方逐级表；越界用表尾 × 增长率近似）。"""
    if level < 1:
        return EXP_TO_NEXT[1]
    if level in EXP_TO_NEXT:
        return EXP_TO_NEXT[level]
    top = max(EXP_TO_NEXT)
    return int(EXP_TO_NEXT[top] * (EXP_TAIL_GROWTH ** (level - top)))


# reqJob 位掩码（WZ 职业组）→ 职业名
REQ_JOB_NAMES = {1: "战士", 2: "魔法师", 4: "弓箭手", 8: "飞侠", 16: "海盗"}


def wear_block(info: Mapping[str, object], level: int,
               stats: Mapping[str, int],
               job: Optional[int] = None) -> Optional[str]:
    """穿戴门控：返回缺失原因提示；可穿返回 None。

    job 传玩家职业码（如 1200）；None 表示跳过职业检查。
    reqJob 为位掩码（1战/2法/4弓/8盗/16海盗），新手不能穿任何限定装备。
    """
    def req(key: str) -> int:
        try:
            return int(info.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    if level < req("reqLevel"):
        return f"等级不足（需 {req('reqLevel')} 级）"
    if job is not None:
        req_job = req("reqJob")
        group_bit = 0 if job // 1000 <= 0 else (1 << (job // 1000 - 1))
        if req_job and not (req_job & group_bit):
            allowed = "/".join(REQ_JOB_NAMES[b] for b in sorted(REQ_JOB_NAMES)
                               if req_job & b)
            return f"该职业无法装备（需 {allowed}）"
    for stat, key in (("str", "reqSTR"), ("dex", "reqDEX"),
                      ("int", "reqINT"), ("luk", "reqLUK")):
        need = req(key)
        if stats.get(stat, 0) < need:
            return f"{STAT_LABELS[stat]}不足（需 {need}）"
    return None
