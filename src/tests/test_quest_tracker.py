"""任务追踪悬浮框：进行中任务的收集/排序/截断/可交付判定，以及绘制落点。

数据走公开接口：伪造 quests（accepted_order / is_accepted / defs）与目标行回调，
不依赖 WZ；绘制只验证面板右对齐到小地图下方、宽度不越视口。
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import List

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()

from game import settings
from game.render.tracker import QuestTracker, build_entries
from game.render.ui import UI
from tests.fake_assets import FakeAssets


def _def(name: str):
    return SimpleNamespace(name=name)


def _quests(order: List[str], accepted: List[str]):
    return SimpleNamespace(
        accepted_order=order,
        is_accepted=lambda qid: qid in accepted,
        defs={qid: _def(f"任务{qid}") for qid in order},
    )


# ── 收集逻辑 ────────────────────────────────────────────────────────
def test_entries_follow_accept_order_and_skip_ghosts():
    """按接取顺序输出，accepted_order 里未接取的 qid 直接跳过。"""
    quests = _quests(["q1", "q2", "q3"], accepted=["q1", "q3"])
    entries = build_entries(quests, None, limit=5,
                            goal_lines=lambda q: [], is_ready=lambda q: False)
    assert [e.qid for e in entries] == ["q1", "q3"]


def test_entries_truncated_to_limit():
    """超过上限只保留前 N 个（含进度行的接取顺序）。"""
    quests = _quests(["a", "b", "c", "d", "e"], accepted=["a", "b", "c", "d", "e"])
    entries = build_entries(quests, None, limit=3,
                            goal_lines=lambda q: [], is_ready=lambda q: False)
    assert [e.qid for e in entries] == ["a", "b", "c"]


def test_entry_carries_title_goals_and_ready_flag():
    """标题取自 defs，进度行走回调，可交付标志由 is_ready 决定。"""
    quests = _quests(["x"], accepted=["x"])
    entries = build_entries(
        quests, None, limit=3,
        goal_lines=lambda q: ["击杀 绿蜗牛 3/7", "收集 蜗牛壳 0/5"],
        is_ready=lambda q: True)
    assert entries[0].title == "任务x"
    assert entries[0].goal_lines == ["击杀 绿蜗牛 3/7", "收集 蜗牛壳 0/5"]
    assert entries[0].ready is True


# ── 可见状态 ────────────────────────────────────────────────────────
def test_tracker_default_hidden_and_toggles():
    tr = QuestTracker()
    assert tr.visible is False
    tr.toggle()
    assert tr.visible is True
    tr.toggle()
    assert tr.visible is False


# ── 绘制几何 ────────────────────────────────────────────────────────
def _tracker_ui() -> UI:
    return UI(FakeAssets())


def test_hidden_tracker_draws_nothing():
    tr = QuestTracker()
    surface = pygame.Surface((settings.VIEW_W, settings.VIEW_H), pygame.SRCALPHA)
    rect = tr.draw(surface, _tracker_ui(),
                   [SimpleNamespace(qid="q", title="任务", goal_lines=[], ready=False)],
                   top=20)
    assert rect is None


def test_empty_entries_draws_nothing():
    tr = QuestTracker()
    tr.toggle()
    surface = pygame.Surface((settings.VIEW_W, settings.VIEW_H), pygame.SRCALPHA)
    assert tr.draw(surface, _tracker_ui(), [], top=20) is None


def test_panel_right_aligned_below_minimap_within_view():
    """面板右缘贴小地图右边距、宽度取小地图宽、整体不越出视口。"""
    tr = QuestTracker()
    tr.toggle()
    surface = pygame.Surface((settings.VIEW_W, settings.VIEW_H), pygame.SRCALPHA)
    entries = [SimpleNamespace(qid=f"q{i}", title="很长的任务名称占位" * 4,
                               goal_lines=["击杀 怪 0/3"], ready=(i == 0))
               for i in range(3)]
    rect = tr.draw(surface, _tracker_ui(), entries, top=30)
    assert rect is not None
    assert rect.right == settings.VIEW_W - settings.MINIMAP_MARGIN
    assert rect.width == settings.MINIMAP_W
    assert rect.top == 30
    assert rect.bottom <= settings.VIEW_H


# ── 进度分子配色 ────────────────────────────────────────────────────
def _draw_single_goal(goal_line: str):
    """画一条进度（ready=False：标题白、前缀中性色，红/绿只可能来自分子）。"""
    tr = QuestTracker()
    tr.toggle()
    surface = pygame.Surface((settings.VIEW_W, settings.VIEW_H), pygame.SRCALPHA)
    entries = [SimpleNamespace(qid="q", title="标题", goal_lines=[goal_line],
                               ready=False)]
    rect = tr.draw(surface, _tracker_ui(), entries, top=30)
    return surface, rect


def _surface_has(surface, rect, pred) -> bool:
    for py in range(rect.top, rect.bottom):
        for px in range(rect.left, rect.right):
            if pred(surface.get_at((px, py))):
                return True
    return False


def _is_red(c) -> bool:
    return c[0] > 170 and c[1] < 140 and c[2] < 140


def _is_green(c) -> bool:
    return c[1] > 170 and c[0] < 170 and c[2] < 170


def test_unmet_numerator_is_red():
    """未达标：分子红、且面板内不含绿色像素。"""
    surface, rect = _draw_single_goal("击杀 绿蜗牛 3/7")
    assert _surface_has(surface, rect, _is_red)
    assert not _surface_has(surface, rect, _is_green)


def test_met_numerator_is_green():
    """达标：分子绿、且面板内不含红色像素。"""
    surface, rect = _draw_single_goal("击杀 绿蜗牛 7/7")
    assert _surface_has(surface, rect, _is_green)
    assert not _surface_has(surface, rect, _is_red)

