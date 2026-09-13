"""强化卷轴：采用官方 204xxxx 物品，成功率与加成以 WZ info 为准。

官方武器攻击/魔力卷轴按武器族分家（见 WEAPON_SCROLL_FAMILIES），每族提供
60% / 30%（诅咒）/ 100%（必成）三档。SCROLLS 只登记「哪些 id 是强化卷轴、
目标栏位与武器前缀」；实际 success/inc* 在施放时由调用方从 Item.wz 的
info 取出传入 apply_scroll。apply_scroll 是纯函数（可单测）：校验栏位与
武器类型、扣强化费（随等级上涨）后 roll 成功/失败——成功把 info 里的
inc* 词条并入 extra、tuc−1；失败仅 tuc−1（装备不销毁，暂不实现诅咒）。
卷轴本体由调用方从背包扣除。
"""

from __future__ import annotations

import random
from typing import Dict, Optional, Tuple

from game import settings
from game.systems.inventory import Item

# ── 武器族：武器 id 前 3 位 → (Item.wz 卷轴 base, 中文名, 是否魔力卷) ──
WEAPON_SCROLL_FAMILIES: Dict[str, Tuple[int, str, bool]] = {
    "130": (20430, "单手剑", False),
    "131": (20431, "单手斧", False),
    "132": (20432, "单手钝器", False),
    "133": (20433, "短剑", False),
    "137": (20437, "短杖", True),
    "138": (20438, "长杖", True),
    "140": (20440, "双手剑", False),
    "141": (20441, "双手斧", False),
    "142": (20442, "双手钝器", False),
    "143": (20443, "枪", False),
    "144": (20444, "矛", False),
    "145": (20445, "弓", False),
    "146": (20446, "弩", False),
    "147": (20447, "拳套", False),
    "148": (20448, "拳甲", False),
    "149": (20449, "短枪", False),
}

# 档位：(item id 后缀, 显示百分比)；对应官方 base+1/5/3
_TIERS: Tuple[Tuple[int, str], ...] = ((1, "60%"), (5, "30%"), (3, "100%"))


def _build_scrolls() -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for prefix, (base, label, magic) in WEAPON_SCROLL_FAMILIES.items():
        kind = "魔力" if magic else "攻击"
        for suffix, pct in _TIERS:
            key = f"{base * 100 + suffix:08d}"
            out[key] = {"slot": "weapon", "weapon": prefix,
                        "name": f"{label}{kind}卷轴 {pct}"}
    return out


SCROLLS: Dict[str, Dict] = _build_scrolls()

# 旧存档里 234 段自制卷轴 → 官方 id（60% / 30% / 100% 映射单手剑档）
LEGACY_SCROLL_IDS: Dict[str, str] = {
    "02340000": "02043001",
    "02340001": "02043005",
    "02340002": "02043003",
}


def normalize_scroll_id(item_id: str) -> str:
    """卷轴 id 归一为 8 位补零字符串（SCROLLS 的键形式）。"""
    try:
        return f"{int(item_id):08d}"
    except (TypeError, ValueError):
        return str(item_id)


def migrate_scroll_id(item_id: str) -> str:
    """旧 234 段卷轴迁移到官方 id；官方卷轴归一 8 位；其余物品原样返回。"""
    norm = normalize_scroll_id(item_id)
    if norm in LEGACY_SCROLL_IDS:
        return LEGACY_SCROLL_IDS[norm]
    if norm in SCROLLS:
        return norm
    return item_id


def is_scroll_id(item_id: str) -> bool:
    """是否为本项目登记的强化卷轴（官方 204xxxx 子集）。"""
    return normalize_scroll_id(item_id) in SCROLLS


def scroll_name(item_id: str) -> Optional[str]:
    """卷轴兜底显示名（无 WZ String 时用）；非登记卷轴返回 None。"""
    sc = SCROLLS.get(normalize_scroll_id(item_id))
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
