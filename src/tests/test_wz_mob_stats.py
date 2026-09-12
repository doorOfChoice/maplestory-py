"""WZ 冒烟：真实 Mob.wz 的 stats 字段映射（无 WZ 环境自动 skip）。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Mob.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_mob_info_exposes_push_and_fly_speed():
    """真实蝙蝠 2300100：stats 含击退抗性 pushed 与飞行速度 flySpeed（非常量 fs）。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        stats = assets.mob_info("2300100")["stats"]
        assert stats["pushed"] == 30
        assert stats["flySpeed"] == 5          # WZ info/flySpeed，而非 fs=10
    finally:
        assets.close()
