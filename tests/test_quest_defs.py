"""精选任务按需解析：只解析请求的 qid，结果与全量解析一致。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Quest.wz").exists(), reason="需要 WZ 资产")


def _assets():
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    return Assets(settings.MAP_ID)


@needs_wz
def test_selective_load_returns_only_requested_qids():
    """传入 qids 时结果集恰好是这些任务（存在的那些）。"""
    from game.quests import load_quest_defs
    assets = _assets()
    try:
        defs = load_quest_defs(assets, {"2088"})
        assert set(defs) == {"2088"}
        assert defs["2088"].end_items  # 研究菇菇怪物：有收集目标
    finally:
        assets.close()


@needs_wz
def test_selective_load_matches_full_parse():
    """按需解析出的 QuestDef 与全量解析逐字段一致。"""
    from game.quests import load_quest_defs
    assets = _assets()
    try:
        part = load_quest_defs(assets, settings.ENABLED_QUESTS)
        full = load_quest_defs(assets)
        assert set(part) == {q for q in settings.ENABLED_QUESTS if q in full}
        for qid, d in part.items():
            assert d == full[qid]
    finally:
        assets.close()
