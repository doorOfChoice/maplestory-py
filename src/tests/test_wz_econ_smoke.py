"""WZ 冒烟：物品 price 字段 / 装备 tuc 字段可读（无 WZ 环境自动 skip）。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings
from game.systems import shop as shop_mod

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Item.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_item_price_and_equip_tuc_readable():
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        # 药水 / 装备 WZ price 字段可读
        assert assets.item_price("02000000") == 25
        assert assets.item_price("02000003") == 100
        assert assets.item_price("01452000") == 10000
        # 官方卷轴 WZ info.price 恒为 1（真实价格由商店脚本定）
        assert assets.item_price("02043001") == 1
        assert shop_mod.item_price("02043001", assets) == 1
        # 装备 tuc（可强化次数）字段可读
        ei = assets.equip_info("01452000") or {}
        assert int(ei.get("tuc") or 0) > 0
    finally:
        assets.close()
