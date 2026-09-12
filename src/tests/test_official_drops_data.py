"""已导入的 079 掉落数据（resources/content/drops.csv）能通过运行时管线加载。

不依赖 WZ，直接验证提交进仓库的生成物：结构与已知怪物的 079 数值。
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from game.systems.drops import OfficialDropTable, load_official_table

DROPS_PATH = (Path(__file__).resolve().parent.parent.parent
              / "resources" / "content" / "drops.csv")


def _raw():
    with DROPS_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_official_table_loads_from_content_file():
    """运行时入口能读到非空掉落表，且覆盖新手怪蓝蜗牛。"""
    table = load_official_table()
    assert table.has_mob("100101")


def test_all_rows_have_valid_item_ids_and_chance():
    """物品 id 为纯数字（"0" 金币行、7 位常规），掉率与数量区间合法。

    掉率文本个别 >100%（如 1000%），运行时按必掉处理。
    """
    for row in _raw():
        item = row["item_id"]
        assert item.isdigit() and 1 <= len(item) <= 9, row
        assert row["chance_text"].endswith("%")
        assert float(row["chance_text"][:-1]) >= 0
        assert 1 <= int(row["min"]) <= int(row["max"])
        assert int(row["questid"]) >= 0


def test_every_mob_has_a_default_meso_row():
    """每只怪都补了一行金币（item_id=0，100%，数量 = 等级 × [2,4]）。"""
    rows = _raw()
    mobs = {r["mob_id"] for r in rows}
    meso = {r["mob_id"] for r in rows if r["item_id"] == "0"}
    assert meso == mobs
    snail = next(r for r in rows if r["mob_id"] == "100101" and r["item_id"] == "0")
    assert (snail["min"], snail["max"], snail["questid"]) == ("4", "8", "0")


def test_quest_conditional_rows_are_exported():
    """任务限定行保留 questid（运行时按进行中任务过滤）。"""
    pig = next(r for r in _raw()
               if r["mob_id"] == "6230100" and r["item_id"] == "4031213")
    assert pig["questid"] == "2097" and pig["chance_text"] == "20%"


def test_blue_snail_official_shell_and_meso_drops():
    """蓝蜗牛 100101：蓝螺壳 4000000（36%）+ 金币 4~8（必掉）。"""
    table = OfficialDropTable.load(DROPS_PATH)
    shell = next(r for r in _raw()
                 if r["mob_id"] == "100101" and r["item_id"] == "4000000")
    assert shell["chance_text"] == "36%"
    res = table.roll("100101", random.Random(0))
    assert 4 <= res.meso <= 8
