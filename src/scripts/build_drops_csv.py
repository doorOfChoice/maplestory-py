#!/usr/bin/env python3
"""把抓取到的 079 掉落表编译为运行时 drops.csv。

输入：
- ``data/mob_drops_079_full.csv`` —— import_drops_079.py 的抓取结果，
  列：mob_id, item_id, chance_text, min, max, questid。
  列 chance_text 形如 "36%" / "0.03%"；为 "-"（网站无法给出概率）的行丢弃。

输出：
- ``resources/content/drops.csv`` —— 运行时唯一事实来源（game.systems.drops
  读取），同上列，另为每只怪补一行默认金币（item_id=0，概率 100%，
  数量区间 = 怪物等级 × [2,4]）。怪物等级取自本地 ``Mob.wz/<id>.img/info/level``，
  不依赖网络。

用法（项目根目录）：
    uv run python src/scripts/build_drops_csv.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import settings

DATA_DIR = Path(__file__).resolve().parent / "data"
SRC_CSV = DATA_DIR / "mob_drops_079_full.csv"
OUT_CSV = settings.RESOURCE_DIR / "content" / "drops.csv"

FIELDS = ["mob_id", "item_id", "chance_text", "min", "max", "questid"]
MESO_ITEM_ID = "0"
MESO_CHANCE_TEXT = "100%"
MESO_MIN_FACTOR = 2
MESO_MAX_FACTOR = 4
_PCT_RE = re.compile(r"^\d+(?:\.\d+)?%$")


def mob_levels() -> dict[int, int]:
    """Mob.wz → {mob_id: level}；读不到等级的怪不入表。"""
    from wzpy.wz_file import WzFile
    wz = WzFile.open(str(settings.WZ_DIR / "Mob.wz"), region=settings.REGION)
    levels: dict[int, int] = {}
    for name, image in wz.root.walk_images():
        if not name.endswith(".img"):
            continue
        try:
            mob_id = int(name[:-4])
        except ValueError:
            continue
        node = image.parse().get("info/level")
        level = int(getattr(node, "value", 0) or 0) if node is not None else 0
        if level > 0:
            levels[mob_id] = level
    return levels


def load_rows() -> list[dict[str, str]]:
    """读抓取 CSV，丢弃概率无法解析（chance_text='-' 等）的行。"""
    rows: list[dict[str, str]] = []
    with SRC_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not _PCT_RE.match(row["chance_text"]):
                continue
            rows.append({k: row[k] for k in FIELDS})
    return rows


def build() -> None:
    levels = mob_levels()
    rows = load_rows()
    mobs = {r["mob_id"] for r in rows}
    missing_level = sorted(m for m in mobs if int(m) not in levels)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        for mob in sorted(mobs, key=int):
            level = levels[int(mob)]
            writer.writerow({
                "mob_id": mob, "item_id": MESO_ITEM_ID,
                "chance_text": MESO_CHANCE_TEXT,
                "min": level * MESO_MIN_FACTOR,
                "max": level * MESO_MAX_FACTOR, "questid": "0",
            })
    print(f"导出 {len(mobs)} 只怪 / {len(rows)} 行物品 + {len(mobs)} 行金币 "
          f"→ {OUT_CSV}")
    if missing_level:
        print(f"警告：{len(missing_level)} 只怪无等级，未补金币：{missing_level[:10]}")


if __name__ == "__main__":
    sys.exit(build())
