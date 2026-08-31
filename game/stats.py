"""数值系统：四维属性、加点、HP/MP 成长、攻防与伤害结算、穿戴门控。

设计哲学：全部为纯函数（输入 dict/int，输出新值），不触碰 WZ 与 pygame，
单测用合成数据即可覆盖。玩家侧（player.py）只负责持有状态并调用这里。

公式（简化版，非官方 v113 全量还原）：
    atk = pad × (1 + 4×主属性/100) + 副属性/10
    dmg = max(1, atk × 技能倍率 × rand(0.95~1.05) − 怪物PDD × (1 − LUK/100))
主属性：弓/弩 → DEX，其余 → STR；副属性取另一维。
"""

from __future__ import annotations

import random
from typing import Dict, Mapping, Optional, Tuple

from . import settings

STAT_KEYS = ("str", "dex", "int", "luk")
STAT_LABELS = {"str": "力量", "dex": "敏捷", "int": "智力", "luk": "幸运"}


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
    """攻击力：武器面板 × 主属性权重 + 副属性/10。"""
    main = stats["dex"] if ranged else stats["str"]
    sub = stats["str"] if ranged else stats["dex"]
    return int(pad * (1 + 4 * main / 100.0) + sub / 10.0)


def roll_damage(atk: int, mult: float, mob_pd: int, luk: int,
                rng: random.Random) -> int:
    """单次命中伤害：atk×倍率×随机(0.95~1.05)，再扣怪物 PDD（LUK 减免）。"""
    raw = int(atk * mult * rng.uniform(0.95, 1.05))
    return max(1, raw - int(mob_pd * (1 - luk / 100.0)))


def defense(stats: Mapping[str, int], equip_pdd: int) -> int:
    """防御力：装备 PDD 总和 + DEX//10。"""
    return equip_pdd + stats["dex"] // 10


def wear_block(info: Mapping[str, object], level: int,
               stats: Mapping[str, int]) -> Optional[str]:
    """穿戴门控：返回缺失原因提示；可穿返回 None。"""
    def req(key: str) -> int:
        try:
            return int(info.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    if level < req("reqLevel"):
        return f"等级不足（需 {req('reqLevel')} 级）"
    for stat, key in (("str", "reqSTR"), ("dex", "reqDEX"),
                      ("int", "reqINT"), ("luk", "reqLUK")):
        need = req(key)
        if stats.get(stat, 0) < need:
            return f"{STAT_LABELS[stat]}不足（需 {need}）"
    return None
