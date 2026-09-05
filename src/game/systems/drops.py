"""官方掉落表（drop_data）运行时数据。

数据源：台服 v113 服务端 SQL 的 drop_data 表，经 src/scripts/import_official_drops.py
提取为 resources/content/drops.json，按 mob 分组，每行
{item, min, max, chance[, quest]}：item 为 "0" 表示金币行，chance 为百万分比
（个别行 >1000000，按必掉处理）；quest 为任务限定行专属，表示需进行中该任务
（quest_id）才会掉。

掷骰模型与服务端一致：逐行独立 roll，命中则在 [min, max] 均匀取数量；
一行都不中则无掉落。金币行命中后合并为一堆。任务限定行只在调用方传入的
进行中任务集（active_quests）含该任务时参与掷骰。
"""

from __future__ import annotations

import json
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


class OfficialDropTable:
    """mob_id → 官方掉落行列表 的只读掷骰表。"""

    def __init__(self, rows_by_mob: Dict[str, List[Dict[str, Any]]]) -> None:
        self._rows: Dict[str, List[Dict[str, Any]]] = {}
        for mid, rows in rows_by_mob.items():
            self._rows.setdefault(_canon_mob_id(mid), []).extend(rows)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "OfficialDropTable":
        return cls(raw)

    @classmethod
    def load(cls, path: Path) -> "OfficialDropTable":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

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
    """加载 resources/content/drops.json（缺文件时空表），进程内缓存。"""
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE
    file = Path(path) if path is not None else settings.RESOURCE_DIR / "content" / "drops.json"
    table = OfficialDropTable.load(file) if file.exists() else OfficialDropTable({})
    if path is None:
        _CACHE = table
    return table
