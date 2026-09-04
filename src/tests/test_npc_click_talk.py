"""点击 NPC 对话：世界坐标命中即路由（寒暄回落）、最上层优先、落空不消费。"""
from __future__ import annotations

import pygame

from game.npc_dialogue import NpcDialogueController


# ── 轻量假世界 ──────────────────────────────────────────────────────
class FakeNPC:
    def __init__(self, npc_id: str, name: str, rect: pygame.Rect) -> None:
        self.npc_id = npc_id
        self.name = name
        self._rect = rect

    def rect(self) -> pygame.Rect:
        return self._rect


class FakePlayer:
    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.quests = None


class FakeWorld:
    def __init__(self, npcs) -> None:
        self.npcs = npcs
        self.player = FakePlayer()


class FakeAssets:
    map_id = "100000000"


class FakeUI:
    def __init__(self) -> None:
        self.shown = []

    def show_dialog(self, npc_name, lines, anchor=None, buttons=None) -> None:
        self.shown.append((npc_name, anchor))


class FakeCtx:
    def __init__(self, npcs) -> None:
        self.world = FakeWorld(npcs)
        self.ui = FakeUI()
        self.assets = FakeAssets()


def make_controller(npcs):
    ctx = FakeCtx(npcs)
    return NpcDialogueController(ctx, {}), ctx


# ── 点击命中 ────────────────────────────────────────────────────────
def test_click_on_npc_opens_its_greeting():
    npc = FakeNPC("9999998", "测试NPC", pygame.Rect(100, 100, 40, 60))
    ctrl, ctx = make_controller([npc])
    assert ctrl.try_talk_at(120, 130) is True
    assert ctx.ui.shown == [("测试NPC", npc)]


def test_click_on_empty_spot_not_consumed():
    npc = FakeNPC("9999998", "测试NPC", pygame.Rect(100, 100, 40, 60))
    ctrl, ctx = make_controller([npc])
    assert ctrl.try_talk_at(10, 10) is False
    assert ctx.ui.shown == []


def test_click_hits_frontmost_npc_when_overlapping():
    back = FakeNPC("9999997", "后面", pygame.Rect(100, 100, 40, 60))
    front = FakeNPC("9999996", "前面", pygame.Rect(100, 100, 40, 60))
    ctrl, ctx = make_controller([back, front])   # front 为后绘制（最上层）
    assert ctrl.try_talk_at(120, 130) is True
    assert ctx.ui.shown == [("前面", front)]


# ── E 键旧行为不回归 ────────────────────────────────────────────────
def test_talk_key_still_requires_npc_at_feet():
    npc = FakeNPC("9999998", "测试NPC", pygame.Rect(100, 100, 40, 60))
    ctrl, ctx = make_controller([npc])
    ctrl.ctx.world.player.x, ctrl.ctx.world.player.y = 120.0, 130.0
    ctrl.try_talk()
    assert ctx.ui.shown == [("测试NPC", npc)]
    ctx.ui.shown.clear()
    ctrl.ctx.world.player.x = 2000.0
    ctrl.try_talk()
    assert ctx.ui.shown == []
