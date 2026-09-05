"""官方掉落表（drop_data）运行时数据。

数据源：台服 v113 服务端 SQL 的 drop_data 表，经 src/scripts/import_official_drops.py
提取为 resources/content/drops.json，按 mob 分组，每行
{item, min, max, chance}：item 为 "0" 表示金币行，chance 为百万分比
（个别行 >1000000，按必掉处理）。

掷骰模型与服务端一致：逐行独立 roll，命中则在 [min, max] 均匀取数量；
一行都不中则无掉落。金币行命中后合并为一堆。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from game import settings


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
             rng: Optional[random.Random] = None) -> DropRoll:
        rng = rng or random
        res = DropRoll()
        for row in self._rows.get(_canon_mob_id(mob_id), []):
            if rng.randrange(1_000_000) >= int(row["chance"]):
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
