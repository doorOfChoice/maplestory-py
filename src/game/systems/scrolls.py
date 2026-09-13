"""强化卷轴：官方 204xxxx 物品统一登记，目标栏位由卷轴 id 类别推导。

官方 204 整段都是强化卷轴。目标装备栏位并不写在 WZ info 里（info 只含
success / inc* / cursed / price / icon 等），只能由卷轴 id 的类别段
（id // 100）判断：20400 头盔、20401/20402 脸眼部、20403 耳环、20404 上衣、
20405 全身、20406 裤裙、20407 鞋、20408 手套、20409 盾、20410 披风，
20430~20449 各武器族。SCROLL_CATEGORIES 是唯一的类别表：is_scroll_id 只做
204 段范围判定，scroll_of 依类别产出 {slot, weapon, name} 描述。

实际 success/inc* 由调用方从 Item.wz 的 info 取出传入 apply_scroll（纯函数）：
校验栏位与武器类型、扣强化费（随等级上涨）后 roll 成功/失败——成功把 info 的
inc* 词条并入 extra、tuc−1；失败仅 tuc−1（装备不销毁，暂不实现诅咒）。
卷轴本体由调用方从背包扣除。名称优先取 String.wz；无 WZ 时武器卷轴回退
「单手剑攻击卷轴 60%」这类，防具回退「披风强化卷轴」这类通用名。
"""

from __future__ import annotations

import random
from typing import Dict, Optional, Tuple

from game import settings
from game.systems.inventory import Item

# ── 卷轴类别表：id // 100 →（目标栏位, 武器族前缀, 中文标签, 是否魔力卷）──
# 武器族前缀为武器 id 前 3 位（01302000 → "130"）；非武器为 None。
# 仅登记本项目已实现栏位的类别（项链/腰带/宠物/特殊卷轴不在表内，
# 仍由 is_scroll_id 识别，但 scroll_of 无目标栏位）。
SCROLL_CATEGORIES: Dict[int, Tuple[str, Optional[str], str, bool]] = {
    20400: ("cap", None, "头盔", False),
    20401: ("face", None, "脸部装饰", False),
    20402: ("face", None, "眼部装饰", False),
    20403: ("earr", None, "耳环", False),
    20404: ("top", None, "上衣", False),
    20405: ("overall", None, "全身铠甲", False),
    20406: ("pants", None, "裤/裙", False),
    20407: ("shoes", None, "鞋子", False),
    20408: ("glove", None, "手套", False),
    20409: ("shield", None, "盾牌", False),
    20410: ("cape", None, "披风", False),
    20430: ("weapon", "130", "单手剑", False),
    20431: ("weapon", "131", "单手斧", False),
    20432: ("weapon", "132", "单手钝器", False),
    20433: ("weapon", "133", "短剑", False),
    20437: ("weapon", "137", "短杖", True),
    20438: ("weapon", "138", "长杖", True),
    20440: ("weapon", "140", "双手剑", False),
    20441: ("weapon", "141", "双手斧", False),
    20442: ("weapon", "142", "双手钝器", False),
    20443: ("weapon", "143", "枪", False),
    20444: ("weapon", "144", "矛", False),
    20445: ("weapon", "145", "弓", False),
    20446: ("weapon", "146", "弩", False),
    20447: ("weapon", "147", "拳套", False),
    20448: ("weapon", "148", "拳甲", False),
    20449: ("weapon", "149", "短枪", False),
}

# 武器卷轴档位：item id 末 3 位 → 显示百分比（对应官方 base+1/5/3）
_TIER_PCT: Dict[int, str] = {1: "60%", 5: "30%", 3: "100%"}

_SCROLL_MIN = 2040000
_SCROLL_MAX = 2049999

# 旧存档里 234 段自制卷轴 → 官方 id（映射单手剑档）
LEGACY_SCROLL_IDS: Dict[str, str] = {
    "02340000": "02043001",
    "02340001": "02043005",
    "02340002": "02043003",
}


def normalize_scroll_id(item_id: str) -> str:
    """卷轴 id 归一为 8 位补零字符串（SCROLL 类别表的键形式）。"""
    try:
        return f"{int(item_id):08d}"
    except (TypeError, ValueError):
        return str(item_id)


def _scroll_int(item_id: str) -> Optional[int]:
    try:
        return int(normalize_scroll_id(item_id))
    except (TypeError, ValueError):
        return None


def is_scroll_id(item_id: str) -> bool:
    """是否官方 204 段强化卷轴（整段识别，含未实现栏位的类别）。"""
    iid = _scroll_int(item_id)
    return iid is not None and _SCROLL_MIN <= iid <= _SCROLL_MAX


def scroll_of(item_id: str) -> Optional[Dict]:
    """卷轴描述 {slot, weapon, name}；非卷轴或游戏未实现该栏位返回 None。"""
    iid = _scroll_int(item_id)
    if iid is None or not (_SCROLL_MIN <= iid <= _SCROLL_MAX):
        return None
    entry = SCROLL_CATEGORIES.get(iid // 100)
    if entry is None:
        return None
    slot, weapon, label, magic = entry
    return {"slot": slot, "weapon": weapon,
            "name": _fallback_name(iid, weapon, label, magic)}


def _fallback_name(iid: int, weapon: Optional[str], label: str,
                   magic: bool) -> str:
    """无 WZ 时的兜底显示名；武器含攻击/魔力与档位，防具用通用名。"""
    if weapon is None:
        return f"{label}强化卷轴"
    kind = "魔力" if magic else "攻击"
    pct = _TIER_PCT.get(iid % 1000)
    return f"{label}{kind}卷轴 {pct}" if pct else f"{label}{kind}卷轴"


def migrate_scroll_id(item_id: str) -> str:
    """旧 234 段卷轴迁移到官方 id；官方卷轴归一 8 位；其余物品原样返回。"""
    norm = normalize_scroll_id(item_id)
    if norm in LEGACY_SCROLL_IDS:
        return LEGACY_SCROLL_IDS[norm]
    if is_scroll_id(norm):
        return norm
    return item_id


def scroll_name(item_id: str) -> Optional[str]:
    """卷轴兜底显示名（无 WZ String 时用）；非卷轴/未实现栏位返回 None。"""
    sc = scroll_of(item_id)
    return sc["name"] if sc else None


def weapon_prefix(item_id: str) -> Optional[str]:
    """武器族前缀（武器 id 前 3 位，如 01302000 → "130"）。"""
    try:
        return str(int(item_id) // 10000)
    except (TypeError, ValueError):
        return None


def scroll_info_of(assets, item_id: str) -> Optional[dict]:
    """从 assets（Item.wz）取卷轴 WZ info（含 success / inc*）；无则 None。"""
    getter = getattr(assets, "consume_info", None)
    if getter is None:
        return None
    try:
        ci = getter(item_id) or {}
    except Exception:
        return None
    return ci.get("info") or {}


def scroll_stats(info: Optional[dict]) -> Tuple[int, Dict[str, int]]:
    """从 WZ info 提取 (成功率, {inc* 词条: 固定值})；缺省 100% 且无加成。"""
    rate = 100
    incs: Dict[str, int] = {}
    if isinstance(info, dict):
        try:
            rate = int(info.get("success", 100))
        except (TypeError, ValueError):
            rate = 100
        for key, val in info.items():
            if isinstance(key, str) and key.startswith("inc"):
                try:
                    incs[key] = int(val)
                except (TypeError, ValueError):
                    continue
    return rate, incs


def scroll_fee(level: int) -> int:
    """强化费用：基础 + 每级增量，随等级上涨。"""
    return settings.SCROLL_FEE_BASE + settings.SCROLL_FEE_PER_LEVEL * max(0, level)


def apply_scroll(scroll: Dict, item: Item, rng: random.Random,
                 level: int = 1, meso: int = 0,
                 info: Optional[dict] = None) -> Optional[Dict]:
    """应用一张卷轴到目标装备（纯函数）。

    目标非装备、栏位不符、武器族不匹配或 tuc≤0 返回 None（卷轴不消耗、
    金币不动）；否则扣强化费，金币不足返回 ok=False / charged=False；
    再按 WZ info 的 success 与 inc* roll 并消耗一次次数。
    返回 {"ok", "charged", "msg", "meso"}。
    """
    if item.kind != "equip" or item.slot != scroll["slot"]:
        return None
    want = scroll.get("weapon")
    if want is not None and weapon_prefix(item.id) != want:
        return None
    if item.tuc <= 0:
        return None
    rate, incs = scroll_stats(info)
    fee = scroll_fee(level)
    if meso < fee:
        return {"ok": False, "charged": False, "msg": f"金币不足（强化费 {fee}）",
                "meso": meso}
    meso -= fee
    if rng.random() * 100 < rate:
        for key, val in incs.items():
            item.extra[key] = item.extra.get(key, 0) + val
        item.tuc -= 1
        gained = " ".join(f"{k} +{v}" for k, v in incs.items())
        msg = f"强化成功！{scroll.get('name', '卷轴')}"
        if gained:
            msg = f"{msg} {gained}"
        return {"ok": True, "charged": True, "msg": msg, "meso": meso}
    item.tuc -= 1
    return {"ok": False, "charged": True,
            "msg": "强化失败，装备未受损（次数-1）", "meso": meso}
