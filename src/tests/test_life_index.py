"""世界生命体索引扫描（需 WZ）：弓箭手村 NPC 应被扫到，任务池过滤后可见任务变多。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Map.wz").exists(), reason="需要 WZ 资产")


def _wz(name):
    pygame.init()
    pygame.display.set_mode((8, 8))
    from wzpy.wz_file import WzFile
    return WzFile.open(str(settings.WZ_DIR / f"{name}.wz"),
                       region=settings.REGION)


@needs_wz
def test_collect_life_ids_finds_town_npcs():
    from game.core.life_index import collect_life_ids
    wz = _wz("Map")
    try:
        npc_ids, mob_ids = collect_life_ids(wz)
    finally:
        wz.close()
    assert "1012100" in npc_ids      # 弓箭手村·汉斯
    assert "1012119" in npc_ids      # 弓箭手村导师
    assert mob_ids                   # 野外怪必然存在


@needs_wz
def test_collect_life_ids_reports_progress():
    """on_progress 回调逐批推进，最后一次 done == total 且 total 为地图数。"""
    from game.core.life_index import collect_life_ids
    calls: list[tuple[int, int]] = []
    wz = _wz("Map")
    try:
        collect_life_ids(wz, on_progress=lambda d, t: calls.append((d, t)))
    finally:
        wz.close()
    assert calls
    assert all(d <= t for d, t in calls)
    assert calls[-1][0] == calls[-1][1] > 1000
    assert [d for d, _ in calls] == sorted(d for d, _ in calls)


@needs_wz
def test_filtered_pool_keeps_gumquest():
    """过滤后的任务池应包含 2088（研究菇菇怪物）——旧白名单的回归保障。"""
    from game.core.life_index import collect_life_ids
    from game.systems.quests import filter_world_quest_defs, load_quest_defs
    map_wz = _wz("Map")
    try:
        npc_ids, mob_ids = collect_life_ids(map_wz)
    finally:
        map_wz.close()
    quest_wz = _wz("Quest")
    assets = type("A", (), {"wz": {"Quest": quest_wz}})()
    defs = load_quest_defs(assets, None)
    kept = filter_world_quest_defs(defs, npc_ids, mob_ids)
    assert "2088" in kept
    # 过滤只是收敛，不应把官方任务砍到比旧白名单还少
    assert len(kept) > 5
