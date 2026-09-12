"""传送门触发行为：碰撞门（pt=3）走进即传、普通门需按↑（合成资产，不依赖 WZ）。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.world import World
from tests.fake_assets import FakeAssets

pygame.init()


def make_world(portals) -> World:
    assets = FakeAssets("100010000")
    assets.portals = portals
    return World(assets, {}, None)


def stand_on(world: World, x: float, y: float) -> None:
    world.player.x = x
    world.player.y = y - settings.FEET_OFFSET


def test_collision_portal_triggers_without_up():
    """碰撞门：玩家脚底重叠即触发，无需按↑。"""
    world = make_world([
        {"name": "sp", "type": 0, "x": 0.0, "y": 0.0, "targetMap": 0},
        {"name": "cs", "type": 3, "x": 0.0, "y": 0.0,
         "targetMap": "200000000", "targetName": "sp"},
    ])
    stand_on(world, 0.0, 0.0)
    portal = world.check_portal(0.016, up_pressed=False)
    assert portal is not None and portal["name"] == "cs"


def test_visible_portal_requires_up():
    """普通门（pt=2）：未按↑不触发，按↑才触发。"""
    world = make_world([
        {"name": "sp", "type": 0, "x": 0.0, "y": 0.0, "targetMap": 0},
        {"name": "pv", "type": 2, "x": 0.0, "y": 0.0,
         "targetMap": "200000000", "targetName": "sp"},
    ])
    stand_on(world, 0.0, 0.0)
    assert world.check_portal(0.016, up_pressed=False) is None
    assert world.check_portal(0.016, up_pressed=True) is not None
