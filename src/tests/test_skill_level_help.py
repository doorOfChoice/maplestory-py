"""技能逐级说明（WZ level.hs → String.wz hN）：SkillDef.help 解析与技能窗 tooltip 注入。"""
from __future__ import annotations

from types import SimpleNamespace

import pygame

from game.systems.skills import SkillDef
from game.render.windows.skill import SkillWindow
from tests.windows_harness import make_services


def test_skill_help_returns_level_text():
    """SkillDef.help(level) 返回该级 WZ 逐级说明；无则空串。"""
    d = SkillDef("2001004", "魔法弹", "", [{"mad": 20}], 1,
                 helps={1: "消费MP6, 基本攻击力20，熟练度15%"})
    assert d.help(1) == "消费MP6, 基本攻击力20，熟练度15%"


def test_skill_help_empty_when_absent():
    """没有逐级说明的技能（旧档/合成技能）help 返回空串，不抛错。"""
    d = SkillDef("9999", "合成", "", [{"damage": 100}], 1)
    assert d.help(1) == ""
    assert d.help(0) == ""


class _Book:
    """最小技能书替身：单技能、已学 1 级、无快捷键。"""

    def __init__(self, d) -> None:
        self.job = 0
        self.defs = {d.id: d}
        self.levels = {d.id: 1}
        self.hotkeys = {}
        self.sp_by_job = {}

    def sp_for_group(self, group: int) -> int:
        return 1

    def skills_for_group(self, group: int) -> list:
        return list(self.defs)

    def learnable(self, owner_group=None) -> list:
        return list(self.defs)

    def can_learn(self, skill_id: str, player_level: int) -> bool:
        return False

    def learn(self, skill_id: str, player_level: int) -> bool:
        return False


def _skill_with_help(help_text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="2001004", name="魔法弹", desc="消耗MP,攻击一个怪物。",
        max_level=1, char_level=1, invisible=False,
        stat=lambda lv, k, d=0: d,
        help=lambda lv, t=help_text: t if lv > 0 else "")


def test_skill_tooltip_includes_level_help():
    """悬停技能行时，tooltip 除总述外还带该级逐级说明（WZ hs）。"""
    d = _skill_with_help("消费MP9, 基本攻击力35，熟练度15%")
    player = SimpleNamespace(skills=_Book(d), level=10)
    svc = make_services(player)
    tips: list = []
    svc.tooltip = tips.append
    win = SkillWindow(svc)
    win.open()
    surface = pygame.Surface((800, 600), pygame.SRCALPHA)

    svc.mouse = lambda: (-1, -1)
    win.draw(surface)                       # 首帧登记行热区
    row = win._drag_rects[0][0]
    svc.mouse = lambda: row.center
    win.draw(surface)                       # 悬停帧产出 tooltip

    assert any("基本攻击力35" in t for t in tips)
