"""脏档防御：死亡瞬间档进门即复活；存档坐标落空则回退入口传送门。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from game.core.physics import Physics
from game.save_manager import SaveManager
from game.world import resolve_saved_spawn


def fh(fid, x1, y1, x2, y2):
    return {"id": fid, "layer": 0, "platform": 0,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "prev": -1, "next": -1}


FLAT = [fh(1, 0, 400, 100, 400)]
FALLBACK = (10.0, 400.0)


def load_written(data: dict) -> dict:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "save.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return SaveManager(path).load()


def test_dead_save_revives_to_full_on_load():
    """hp=0 的脏档：读取时满血复活，避免进门即死→原地重生的死循环。"""
    data = load_written({"version": 4,
                         "player": {"hp": 0, "max_hp": 1550}})
    assert data["player"]["hp"] == 1550


def test_healthy_save_hp_untouched():
    data = load_written({"version": 4,
                         "player": {"hp": 123.5, "max_hp": 1550}})
    assert data["player"]["hp"] == 123.5


def test_saved_spawn_deep_below_ground_falls_back():
    """存档坐标埋在地面线下千米（坠落中被写入）：判无效，回退出生门。"""
    p = Physics(FLAT, [])
    assert resolve_saved_spawn(p, (50.0, 1370.0), FALLBACK) == FALLBACK


def test_saved_spawn_near_ground_is_kept():
    """正常地面附近的存档坐标原样保留。"""
    p = Physics(FLAT, [])
    assert resolve_saved_spawn(p, (50.0, 404.0), FALLBACK) == (50.0, 404.0)


def test_saved_spawn_none_uses_fallback():
    p = Physics(FLAT, [])
    assert resolve_saved_spawn(p, None, FALLBACK) == FALLBACK
