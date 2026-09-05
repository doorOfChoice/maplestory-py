#!/usr/bin/env python3
"""把官方 v113 商店货架导入为 content/npc/<id>.lua 的 shops()。

数据源：data/official_shops.csv —— 提取自台服 v113 服务端
（github.com/Neillife/MapleStory-v113-Server-Eimulator，sql/e113.sql）的
`shops` + `shopitems` 两张表，列：npc_id, shop_id, item_id, price, position。

本项目约定 Lua 是商店的唯一事实来源（见 resources/content/AGENTS.md），
因此不直连 SQL，而是离线生成每个 NPC 一份 npc/<id>.lua（只含 shops()，
一个官方 shopid = 一个页签，按 position 排序、同店重复物品保留首个）。

NPC 显示名从本地 String.wz 查询（写文件头注释用）；无 WZ 时回退 npc_id。
已存在 npc/<id>.lua 的 NPC 默认跳过（不覆盖手写脚本），--force 亦不覆盖。

用法（项目根目录）：
    uv run python src/scripts/import_official_shops.py
"""

from __future__ import annotations

import csv
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = Path(__file__).resolve().parent / "data" / "official_shops.csv"
NPC_DIR = PROJECT_ROOT / "resources" / "content" / "npc"

_TEMPLATE = """-- {npc_id}{name_note}：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {{}}

function M.shops()
  return {{
{shops}  }}
end

return M
"""

_SHOP_TEMPLATE = """    {{
      shop_id = "{shop_id}",
      name = "{name}",
      items = {{
{items}      }}
    }},
"""


def load_shops() -> "OrderedDict[str, OrderedDict[str, list]]":
    """csv → {npc_id: {shop_id: [(item_id, price), ...]}}（position 序、去重）。"""
    out: "OrderedDict[str, OrderedDict[str, list]]" = OrderedDict()
    seen: "OrderedDict[str, set]" = OrderedDict()
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            npc = out.setdefault(row["npc_id"], OrderedDict())
            shop = npc.setdefault(row["shop_id"], [])
            items = seen.setdefault(row["shop_id"], set())
            item_id = str(int(row["item_id"])).zfill(8)
            if item_id in items:
                continue
            items.add(item_id)
            shop.append((item_id, int(row["price"])))
    return out


def npc_names(npc_ids: list) -> dict:
    """从 String.wz 批量查 NPC 名（繁→简）；WZ 缺失或出错时返回空表。"""
    try:
        from game.core.localize import to_simplified
        from wzpy.wz_file import WzFile
        wz = WzFile.open(str(settings.WZ_DIR / "String.wz"),
                         region=settings.REGION)
        image = wz.root.get("Npc.img")
        parsed = image.parse() if image else {}
        names = {}
        for npc_id in npc_ids:
            node = parsed.get(str(int(npc_id)))
            entry = node.get("name").value if node and node.get("name") else None
            if entry:
                names[npc_id] = to_simplified(str(entry))
        return names
    except Exception:
        return {}


def render(npc_id: str, npc_name: str | None,
           shops: "OrderedDict[str, list]") -> str:
    blocks = []
    for i, (shop_id, items) in enumerate(shops.items(), start=1):
        lines = "".join(f'        {{item_id = "{iid}", price = {price}}},\n'
                        for iid, price in items)
        name = "商店" if len(shops) == 1 else f"商店{i}"
        blocks.append(_SHOP_TEMPLATE.format(shop_id=f"{npc_id}_shop_{i}",
                                            name=name, items=lines))
    note = f"（{npc_name}）" if npc_name else ""
    return _TEMPLATE.format(npc_id=npc_id, name_note=note, shops="".join(blocks))


def main() -> None:
    shops_by_npc = load_shops()
    names = npc_names(list(shops_by_npc))
    NPC_DIR.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for npc_id, shops in shops_by_npc.items():
        path = NPC_DIR / f"{npc_id}.lua"
        if path.exists():
            print(f"跳过（已存在手写脚本）: {path.name}")
            skipped += 1
            continue
        path.write_text(render(npc_id, names.get(npc_id), shops),
                        encoding="utf-8")
        written += 1
    print(f"完成：生成 {written} 份、跳过 {skipped} 份 → {NPC_DIR}")


if __name__ == "__main__":
    main()
