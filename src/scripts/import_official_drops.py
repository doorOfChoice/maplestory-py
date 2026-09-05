#!/usr/bin/env python3
"""把官方 v113 怪物掉落表（drop_data）导入为 resources/content/drops.json。

数据源：data/official_drops.csv —— 提取自台服 v113 服务端
（github.com/Neillife/MapleStory-v113-Server-Eimulator，sql/e113.sql）的
`drop_data` 表，列：mob_id, item_id, min_qty, max_qty, quest_id, chance。

产物为运行时 JSON：{mob_id: [{item, min, max, chance}, ...]}，
item "0" 表示金币行；quest_id > 0 的任务限定行不导出（本项目任务掉落
走 content/lua entries() 自管）。运行期由 game.systems.drops 读取，
掷骰模型见该模块 docstring。

用法（项目根目录）：
    uv run python src/scripts/import_official_drops.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = Path(__file__).resolve().parent / "data" / "official_drops.csv"
OUT_PATH = PROJECT_ROOT / "resources" / "content" / "drops.json"


def build_table(csv_path: Path = CSV_PATH) -> "OrderedDict[str, list]":
    """CSV → 按 mob 分组的行列表；过滤任务限定行并校验数值范围。"""
    table: "OrderedDict[str, list]" = OrderedDict()
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row["quest_id"]) > 0:
                continue
            chance = int(row["chance"])
            lo, hi = int(row["min_qty"]), int(row["max_qty"])
            if chance < 0 or lo < 1 or hi < lo:
                raise ValueError(f"非法掉落行: {row}")
            table.setdefault(row["mob_id"], []).append({
                "item": str(int(row["item_id"])),
                "min": lo, "max": hi, "chance": chance,
            })
    return table


def main() -> None:
    table = build_table()
    rows = sum(len(v) for v in table.values())
    OUT_PATH.write_text(
        json.dumps(table, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    print(f"导出 {len(table)} 个怪物 / {rows} 行掉落 → {OUT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
