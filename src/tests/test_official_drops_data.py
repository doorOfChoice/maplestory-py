"""已导入的官方掉落数据（resources/content/drops.json）能通过运行时管线加载。

不依赖 WZ，直接验证提交进仓库的生成物：结构与已知怪物的官方数值。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from game.systems.drops import OfficialDropTable, load_official_table

DROPS_PATH = (Path(__file__).resolve().parent.parent.parent
              / "resources" / "content" / "drops.json")


def _raw():
    return json.loads(DROPS_PATH.read_text(encoding="utf-8"))


def test_official_table_loads_from_content_file():
    """运行时入口能读到非空官方表，且覆盖新手怪蓝蜗牛。"""
    table = load_official_table()
    assert table.has_mob("100101")


def test_all_rows_have_valid_item_ids_and_chance():
    """物品 id 为纯数字（"0" 金币行、7 位常规、9 位宠物/特殊类），掉率与数量区间合法。"""
    for mob_id, rows in _raw().items():
        assert str(int(mob_id)) == mob_id
        for row in rows:
            item = row["item"]
            assert item.isdigit() and 1 <= len(item) <= 9, mob_id
            assert row["chance"] >= 0
            assert 1 <= row["min"] <= row["max"]
            assert int(row.get("quest", 0)) >= 0


def test_quest_conditional_rows_are_exported():
    """任务限定行保留在生成物中并带 quest 字段（运行时按进行中任务过滤）。"""
    quest_rows = [r for rows in _raw().values() for r in rows
                  if int(r.get("quest", 0)) > 0]
    assert len(quest_rows) == 406
    pig = next(r for r in _raw()["6230100"] if r["item"] == "4031213")
    assert pig["quest"] == 2097 and pig["chance"] == 200_000


def test_blue_snail_official_meso_and_shell_drops():
    """蓝蜗牛 100101：金币 8~12（40%）+ 蓝螺壳 4000000（60%），与服务端一致。"""
    table = OfficialDropTable.load(DROPS_PATH)
    rows = _raw()["100101"]
    meso = next(r for r in rows if r["item"] == "0")
    assert (meso["min"], meso["max"], meso["chance"]) == (8, 12, 400_000)
    shell = next(r for r in rows if r["item"] == "4000000")
    assert shell["chance"] == 600_000
    res = table.roll("100101", random.Random(0))
    assert res.meso == 0 or 8 <= res.meso <= 12
