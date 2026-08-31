"""WZ 冒烟：真实 Skill.wz 弓箭手树解析（无 WZ 环境自动 skip）。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Skill.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_bowman_tree_contains_bowman_skills():
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    from game.jobs import skill_ids_for_job
    from game.skills import load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        ids = skill_ids_for_job(assets, 3000)
        assert "3001004" in ids
        defs = load_skill_defs(assets, ["3001004", "3001005"])
        assert defs["3001004"].name == "断魂箭"
        assert defs["3001005"].req == {"3001004": 1}
        assert defs["3001004"].stat(1, "mpCon") == 7
        assert defs["3001005"].stat(1, "bulletCount") == 2
        assert assets.skill_ball_frames("3001004")
        assert assets.skill_icon("3001004") is not None
    finally:
        assets.close()
