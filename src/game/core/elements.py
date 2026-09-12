"""属性克制：WZ elemAttr ↔ 伤害倍率（纯函数，无 WZ/pygame 依赖）。

两侧编码：
· 怪物 Mob.wz/<id>.img/info/elemAttr，如 "F3S2"（大写字母+数字），
  数字 1=免疫、2=抵抗、3=弱点，未列出的元素视为中性。
· 技能 Skill.wz/<img>/skill/<id>/elemAttr，如 "f"/"i"/"l"/"s"/"h"（单字符）。
元素字母统一：f=火、i=冰、l=雷、s=毒、h=圣、d=暗、p=物理。

伤害倍率沿用旧版（v113 前后）客户端取值：弱点 ×1.5、抵抗 ×0.5、免疫 → 1 点
（倍率 0.0，由调用方 max(1,...) 兜底）。
"""

from __future__ import annotations

from typing import Dict, Mapping

WEAK = 1.5
STRONG = 0.5
IMMUNE = 0.0
NEUTRAL = 1.0


def parse_elem_attr(text) -> Dict[str, int]:
    """把 WZ elemAttr 字符串解析成 {元素字母小写: 等级}。

    "F3"→{"f":3}、"I2F3"→{"i":2,"f":3}；空/None/非法字符静默忽略。
    """
    out: Dict[str, int] = {}
    if not text:
        return out
    cur = ""
    for ch in str(text):
        if ch.isalpha():
            cur = ch.lower()
            out.setdefault(cur, 0)
        elif ch.isdigit() and cur:
            out[cur] = int(ch)
    return out


def element_multiplier(mob_elem: Mapping[str, int], skill_element) -> float:
    """技能元素对某怪的伤害倍率（mob_elem 由 parse_elem_attr 得到）。"""
    if not skill_element:
        return NEUTRAL
    letter = str(skill_element).strip().lower()[:1]
    level = mob_elem.get(letter)
    if level == 3:
        return WEAK
    if level == 2:
        return STRONG
    if level == 1:
        return IMMUNE
    return NEUTRAL
