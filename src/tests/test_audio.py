"""音频：音效播放与 MobDeath 死亡音效资源查找。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Sound.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_mob_death_sound_bytes_found_for_known_mob():
    """Sound.wz 中应能找到已知怪物的死亡音效字节。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    data = assets.mob_death_sound_bytes("100101")
    assert data is not None
    assert len(data) > 0


@needs_wz
def test_mob_death_sound_bytes_missing_mob_returns_none():
    """不存在的怪物 ID 应返回 None 而非报错。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    data = assets.mob_death_sound_bytes("9999999")
    assert data is None