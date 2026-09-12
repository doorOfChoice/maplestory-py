"""079 掉落表（drops.csv）运行时数据。

数据源：冒险岛 079 小册子（mxd079.dvg.cn）的掉落数据，经
src/scripts/import_drops_079.py 抓取、src/scripts/build_drops_csv.py 编译为
resources/content/drops.csv，列：mob_id, item_id, chance_text, min, max,
questid。运行时按 mob 分组为 {item, min, max, chance[, quest]}：item 为 "0"
表示金币行，chance 为百万分比（由 chance_text 如 "36%" / "0.03%" 换算）；
quest 为任务限定行专属，表示需进行中该任务（quest_id）才会掉。

掷骰模型：逐行独立 roll，命中则在 [min, max] 均匀取数量；一行都不中则
无掉落。金币行命中后合并为一堆。任务限定行只在调用方传入的进行中任务集
（active_quests）含该任务时参与掷骰。
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from game import settings

# 装备掉落倍率（/droprate 指令设置，>=1）；只作用于装备（item 首位 1）行。
_EQUIP_DROP_MULT = 1.0


def set_equip_drop_mult(value: float) -> None:
    """设置装备掉落倍率（>=1，来自 /droprate 指令）；持久到进程内存。"""
    global _EQUIP_DROP_MULT
    _EQUIP_DROP_MULT = max(1.0, float(value))


def equip_drop_mult() -> float:
    """读取当前装备掉落倍率（默认 1.0 = 无加成）。"""
    return _EQUIP_DROP_MULT


def scaled_equip_rate(base_rate: float) -> float:
    """装备掉率 × 当前倍率，封顶 1.0（必掉）。"""
    return min(1.0, base_rate * _EQUIP_DROP_MULT)


@dataclass
class DropRoll:
    """一次击杀的掉落结算结果。"""

    meso: int = 0
    items: List[Dict[str, Any]] = field(default_factory=list)


def _canon_mob_id(mob_id: Any) -> str:
    """怪 id 归一：WZ 带前导零（0100101），SQL 是纯数字（100101），同键才命中。"""
    try:
        return str(int(mob_id))
    except (TypeError, ValueError):
        return str(mob_id)


def parse_chance_text(text: str) -> int:
    """把 "36%" / "0.03%" 换算为百万分比整数（36% → 360000）。"""
    s = str(text).strip()
    if not s.endswith("%"):
        raise ValueError(f"无法解析掉率文本: {text!r}")
    return round(float(s[:-1]) * 10_000)


class OfficialDropTable:
    """mob_id → 掉落行列表 的只读掷骰表。"""

    def __init__(self, rows_by_mob: Dict[str, List[Dict[str, Any]]]) -> None:
        self._rows: Dict[str, List[Dict[str, Any]]] = {}
        for mid, rows in rows_by_mob.items():
            self._rows.setdefault(_canon_mob_id(mid), []).extend(rows)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "OfficialDropTable":
        return cls(raw)

    @classmethod
    def load(cls, path: Path) -> "OfficialDropTable":
        """读 drops.csv（列 mob_id,item_id,chance_text,min,max,questid）。"""
        rows_by_mob: Dict[str, List[Dict[str, Any]]] = {}
        with Path(path).open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entry: Dict[str, Any] = {
                    "item": str(int(row["item_id"])),
                    "min": int(row["min"]),
                    "max": int(row["max"]),
                    "chance": parse_chance_text(row["chance_text"]),
                }
                quest = int(row.get("questid") or 0)
                if quest > 0:
                    entry["quest"] = quest
                rows_by_mob.setdefault(row["mob_id"], []).append(entry)
        return cls(rows_by_mob)

    def has_mob(self, mob_id: str) -> bool:
        return _canon_mob_id(mob_id) in self._rows

    def roll(self, mob_id: str,
             rng: Optional[random.Random] = None,
             active_quests: Optional[Set[str]] = None) -> DropRoll:
        """掷骰一个怪的掉落行；任务限定行仅当 quest 在 active_quests 内才参与。"""
        rng = rng or random
        res = DropRoll()
        for row in self._rows.get(_canon_mob_id(mob_id), []):
            quest = int(row.get("quest", 0) or 0)
            if quest > 0 and str(quest) not in (active_quests or ()):
                continue
            chance = int(row["chance"])
            if str(row["item"]).startswith("1"):
                chance = min(1_000_000, chance * _EQUIP_DROP_MULT)
            if rng.randrange(1_000_000) >= chance:
                continue
            qty = rng.randint(int(row["min"]), int(row["max"]))
            if str(row["item"]) == "0":
                res.meso += qty
            else:
                res.items.append({"id": str(row["item"]), "count": qty})
        return res


# ── 运行时单例 ───────────────────────────────────────────────────────
_CACHE: Optional[OfficialDropTable] = None


def load_official_table(path: Optional[Path] = None) -> OfficialDropTable:
    """加载 resources/content/drops.csv（缺文件时空表），进程内缓存。"""
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE
    file = Path(path) if path is not None else settings.RESOURCE_DIR / "content" / "drops.csv"
    table = OfficialDropTable.load(file) if file.exists() else OfficialDropTable({})
    if path is None:
        _CACHE = table
    return table
