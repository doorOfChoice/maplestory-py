"""任务追踪悬浮框：右上角小地图下方常驻一小面板，显示最多 N 个进行中任务。

沿用原版「进行中的任务」窗体手感：每块 = 任务标题 + 逐条目标进度（击杀 / 收集），
可交付的任务整块高亮并打「可交付」标记。数据全部经 QuestLog 公开接口取（见
build_entries），本模块不含 WZ 依赖；目标行的文案格式化由 game 层注入。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pygame

from game import settings
from game.render.windows.core.widgets import ellipsize

# ── 面板内布局常量 ──────────────────────────────────────────────────
PAD = 6                      # 面板内边距
ENTRY_GAP = 5                # 任务块之间的间隔
TITLE_GOAL_GAP = 3           # 任务标题与首行进度的间距
BG_ALPHA = 150               # 半透明底板黑（与小地图/名牌同调）
TITLE_COLOR = (255, 255, 255)
READY_COLOR = (150, 255, 150)
GOAL_COLOR = (206, 206, 196)
NUM_TODO_COLOR = (240, 90, 80)    # 进度分子未达标：红
NUM_DONE_COLOR = (120, 240, 120)  # 进度分子达标：绿

_PROGRESS_RE = re.compile(r"^(.*?)(\d+)\s*/\s*(\d+)$")


@dataclass
class TrackerEntry:
    """一个进行中任务的追踪行：标题 + 目标进度行 + 是否可交付。"""

    qid: str
    title: str
    goal_lines: List[str] = field(default_factory=list)
    ready: bool = False


def build_entries(quests, player, limit: int,
                  goal_lines: Callable[[str], List[str]],
                  is_ready: Callable[[str], bool]) -> List[TrackerEntry]:
    """收集进行中任务：按接取顺序、跳过未接取/无定义者、截断到 limit。

    goal_lines(qid) 返回该任务的进度文本行；is_ready(qid) 判定能否交付（高亮）。
    """
    entries: List[TrackerEntry] = []
    for qid in getattr(quests, "accepted_order", []):
        if len(entries) >= limit:
            break
        if not quests.is_accepted(qid):
            continue
        d = quests.defs.get(qid)
        if d is None:
            continue
        entries.append(TrackerEntry(qid=qid, title=d.name,
                                    goal_lines=list(goal_lines(qid)),
                                    ready=is_ready(qid)))
    return entries


class QuestTracker:
    """追踪框的可见状态（O 键 toggle）与每帧绘制。"""

    def __init__(self) -> None:
        self.visible = False

    def toggle(self) -> None:
        self.visible = not self.visible

    def _title_font(self, ui):
        return ui.font

    def _goal_font(self, ui):
        return ui.font_small

    def _panel_height(self, ui, entries: List[TrackerEntry]) -> int:
        th = self._title_font(ui).get_height()
        gh = self._goal_font(ui).get_height()
        h = PAD * 2 + th * len(entries) + ENTRY_GAP * (len(entries) - 1)
        h += sum(gh * len(e.goal_lines) for e in entries)
        h += sum(TITLE_GOAL_GAP for e in entries if e.goal_lines)
        return h

    def _draw_goal_line(self, surface, font, x: int, y: int, max_w: int,
                        line: str) -> None:
        """渲染一行进度：行尾的 n/m 中分子按达标与否染红/绿，其余走常规配色。"""
        m = _PROGRESS_RE.match(line.strip())
        if not m:
            surface.blit(font.render(ellipsize(line, font, max_w), True, GOAL_COLOR),
                         (x, y))
            return
        prefix, num, total = m.group(1), m.group(2), m.group(3)
        done = int(num) >= int(total)
        tail = f"/{total}"
        avail = max_w - font.size(num)[0] - font.size(tail)[0]
        if font.size(prefix)[0] > avail:
            prefix = ellipsize(prefix, font, max(0, avail))
        cx = x
        for text, color in ((prefix, GOAL_COLOR),
                            (num, NUM_DONE_COLOR if done else NUM_TODO_COLOR),
                            (tail, GOAL_COLOR)):
            if not text:
                continue
            surf = font.render(text, True, color)
            surface.blit(surf, (cx, y))
            cx += surf.get_width()

    def draw(self, surface, ui, entries: List[TrackerEntry],
             top: int) -> Optional[pygame.Rect]:
        """把追踪框画在右上角（top 由调用方给出，通常为小地图/名牌下方）。

        隐藏或无进行中任务时不绘制，返回 None；否则返回面板矩形。
        """
        if not self.visible or not entries:
            return None
        w = settings.MINIMAP_W
        x = surface.get_width() - w - settings.MINIMAP_MARGIN
        h = self._panel_height(ui, entries)
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (0, 0, 0, BG_ALPHA), (0, 0, w, h), border_radius=6)
        surface.blit(bg, (x, top))

        tf = self._title_font(ui)
        gf = self._goal_font(ui)
        th = tf.get_height()
        gh = gf.get_height()
        inner = w - 2 * PAD
        cy = top + PAD
        for e in entries:
            tag_w = 0
            if e.ready:
                tag = gf.render("可交付", True, READY_COLOR)
                tag_w = tag.get_width()
                surface.blit(tag, (x + w - PAD - tag_w,
                                   cy + (th - gh) // 2))
            title = ellipsize(e.title, tf, inner - tag_w - 4)
            surface.blit(tf.render(
                title, True, READY_COLOR if e.ready else TITLE_COLOR),
                (x + PAD, cy))
            cy += th
            if e.goal_lines:
                cy += TITLE_GOAL_GAP
            for line in e.goal_lines:
                self._draw_goal_line(surface, gf, x + PAD, cy, inner, line)
                cy += gh
            cy += ENTRY_GAP
        return pygame.Rect(x, top, w, h)
