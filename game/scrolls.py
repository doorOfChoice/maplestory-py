"""强化卷轴：自制配置与卷轴应用（纯函数，可单测）。

Item.wz 没有 234 类目，故卷轴物品 id 使用 234xxxxx 段自造（与其他物品不冲突，
id 以补零 8 位存储）。apply_scroll 校验目标栏位与剩余强化次数，扣强化费
（随等级上涨）后 roll 成功/失败：成功 → 词条并入 extra、tuc−1；失败 →
仅 tuc−1（装备不销毁，简化）。卷轴本体由调用方从背包扣除。
"""

from __future__ import annotations

import random
from typing import Dict, Optional

from . import settings
from .inventory import Item

# ── 卷轴配置（8 位补零 id → 名称 / 目标栏位 / 成功率% / 加成区间 / 词条）────
SCROLLS: Dict[str, Dict] = {
    "02340000": {"name": "武器攻击力卷轴 60%", "slot": "weapon",
                 "rate": 60, "min": 2, "max": 4, "stat": "incPAD"},
    "02340001": {"name": "武器攻击力卷轴 30%", "slot": "weapon",
                 "rate": 30, "min": 4, "max": 7, "stat": "incPAD"},
    "02340002": {"name": "武器攻击力卷轴 100%", "slot": "weapon",
                 "rate": 100, "min": 1, "max": 2, "stat": "incPAD"},
}


def is_scroll_id(item_id: str) -> bool:
    """判断是否为自制卷轴 id（234xxxxx 段）。"""
    try:
        return settings.SCROLL_ID_MIN <= int(item_id) < settings.SCROLL_ID_MAX
    except (TypeError, ValueError):
        return False


def scroll_fee(level: int) -> int:
    """强化费用：基础 + 每级增量，随等级上涨。"""
    return settings.SCROLL_FEE_BASE + settings.SCROLL_FEE_PER_LEVEL * max(0, level)


def apply_scroll(scroll: Dict, item: Item, rng: random.Random,
                 level: int = 1, meso: int = 0) -> Optional[Dict]:
    """应用一张卷轴到目标装备（纯函数）。

    栏位不符或 tuc≤0 返回 None（卷轴不消耗、金币不动）；否则扣强化费，
    金币不足返回 ok=False / charged=False；再 roll 成功/失败并消耗一次次数。
    返回 {"ok", "charged", "msg", "meso"}。
    """
    if item.slot != scroll["slot"] or item.tuc <= 0:
        return None
    fee = scroll_fee(level)
    if meso < fee:
        return {"ok": False, "charged": False, "msg": f"金币不足（强化费 {fee}）",
                "meso": meso}
    meso -= fee
    if rng.random() * 100 < scroll["rate"]:
        delta = rng.randint(scroll["min"], scroll["max"])
        item.extra[scroll["stat"]] = item.extra.get(scroll["stat"], 0) + delta
        item.tuc -= 1
        return {"ok": True, "charged": True,
                "msg": f"强化成功！{scroll['name']} +{delta}", "meso": meso}
    item.tuc -= 1
    return {"ok": False, "charged": True,
            "msg": "强化失败，装备未受损（次数-1）", "meso": meso}
