"""左下角 buff 图标带：召唤物也作为一行，显示技能图标与剩余时间灰蒙层。

与 buff / 状态异常共用同一条图标带（duck-typing：skill_id/name/remaining/total）；
召唤进栏、倒计时遮罩随剩余时间变化 —— 全部走 UI.draw_hud 公开接口，不依赖 WZ。
"""

from __future__ import annotations

from types import SimpleNamespace

import pygame

pygame.init()

from game.render.ui import UI

VIEW = (960, 540)
BAR = 28
ICON = 32
SUMMON_COLOR = (255, 0, 220)


# ── 合成素材与假实体 ────────────────────────────────────────────────
class _Assets:
    """任意 UI 图返回空白小图；召唤技能图标返回纯色方块以便断言。"""

    def ui_surface(self, img: str, path: str):
        return pygame.Surface((BAR, BAR), pygame.SRCALPHA), (0, 0)

    def skill_icon(self, skill_id: str):
        icon = pygame.Surface((ICON, ICON), pygame.SRCALPHA)
        icon.fill(SUMMON_COLOR)
        return icon

    def item_icon(self, item_id: str):
        return None


class _Player:
    hp = max_hp = 100
    mp = max_mp = 50
    exp = 0
    level = 1

    def exp_to_next(self) -> int:
        return 100


class _Combat:
    total_kills = 0
    meso = 0

    def __init__(self, summons=()) -> None:
        self.summons = list(summons)


def summon(remaining: float = 50.0, total: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(skill_id="3111005", name="银鹰召唤",
                           remaining=remaining, total=total)


def draw_hud(combat: _Combat) -> pygame.Surface:
    ui = UI(_Assets())
    surface = pygame.Surface(VIEW, pygame.SRCALPHA)
    ui.draw_hud(surface, _Player(), combat)
    return surface


def icon_xy() -> tuple:
    """buff 带首格坐标：状态栏靠左上方（与 _draw_effect_icons 定位公式一致）。"""
    bx = (VIEW[0] - BAR) // 2
    by = VIEW[1] - BAR
    return bx, by - 30


def test_summon_icon_rendered_in_effect_bar():
    """召唤存在时，其技能图标出现在左下角 buff 带（未被遮罩覆盖的下半部）。"""
    surface = draw_hud(_Combat([summon(remaining=50.0, total=100.0)]))
    x, y = icon_xy()
    assert surface.get_at((x + ICON // 2, y + ICON - 4))[:3] == SUMMON_COLOR


def test_summon_veil_absent_at_full_time():
    surface = draw_hud(_Combat([summon(remaining=100.0, total=100.0)]))
    x, y = icon_xy()
    assert surface.get_at((x + ICON // 2, y + 2))[:3] == SUMMON_COLOR


def test_summon_veil_covers_icon_when_expired():
    surface = draw_hud(_Combat([summon(remaining=0.0, total=100.0)]))
    x, y = icon_xy()
    assert surface.get_at((x + ICON // 2, y + 2))[:3] != SUMMON_COLOR


def test_no_summon_no_icon():
    surface = draw_hud(_Combat([]))
    x, y = icon_xy()
    assert surface.get_at((x + ICON // 2, y + ICON // 2))[:3] != SUMMON_COLOR
