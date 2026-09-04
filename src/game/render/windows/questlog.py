"""任务日志窗（Q 键）：UIWindow/Quest 底板，列出进行中任务的名称/目标 NPC/目标行。

1:1 迁移旧 panels._draw_questlog：任务名与目标行先经 render_markup 脱标签、
再按面板可用宽度折行；目标行数据来自 svc.quest_goal_lines 回调（Game 注入）。
底部为状态栏预留 BAR_RESERVE 高度；素材缺失回退自绘 panel_frame。
坐标约定：事件 pos 为内部视口（VIEW）坐标。
"""

from __future__ import annotations

from typing import List, Tuple

from game.render.windows.core import widgets
from game.render.windows.core.window import Window
from game.systems.quests import render_markup

# ── 原版窗口几何（由 panels.py 迁移）───────────────────────────────
QST_BG = "Quest/backgrnd2"
QST_W, QST_H = 305, 396
QST_ROW_H = 26           # 每行任务条目高度
BAR_RESERVE = 58         # 底部状态栏预留高度（无 StatusBar 素材时同值）


class QuestLogWindow(Window):
    """任务日志：进行中任务按接取顺序逐条展示。"""

    key = "questlog"

    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (vw - QST_W - 4, vh - QST_H - BAR_RESERVE - 2)

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    # ── 文本 ───────────────────────────────────────────────────────
    def _wrap_text(self, text: str, width: int, font) -> List[str]:
        """脱标签后按宽度折行（允许 \\n 分段），确保不溢出面板边界。"""
        cleaned = render_markup(text,
                                map_name=self.svc.assets.map_name_of,
                                npc_name=self.svc.assets.npc_name,
                                item_name=self.svc.assets.item_name,
                                mob_name=self.svc.assets.mob_name_of)
        lines: List[str] = []
        for seg in cleaned.split("\n"):
            lines.extend(self.svc.ui._wrap(seg, width, font))
        return lines or [""]

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        player = self.svc.player()
        bg = widgets.wz_surface(self.svc, QST_BG)
        x, y = self.place(surface, (QST_W, QST_H))
        if bg is not None:
            surface.blit(bg, (x, y))
        else:
            widgets.panel_frame(surface, self.rect)
        self.add_chrome(surface, x, y, QST_W, 24)

        quests = player.quests
        # 收集进行中任务（保持接取顺序）
        active = [qid for qid in quests.accepted_order
                  if quests.is_accepted(qid)]

        # 标题（backgrnd2 为浅底，文字用深色）
        surface.blit(f.render("任务日志 (Q)", True, (60, 52, 44)),
                     (x + 12, y + 4))
        count = fs.render(f"进行中 {len(active)}", True, (120, 108, 92))
        surface.blit(count, (x + QST_W - count.get_width() - 40, y + 7))

        if not active:
            empty = fs.render("目前没有进行中的任务", True, (120, 108, 92))
            surface.blit(empty, (x + 20, y + 60))
            return

        ty = y + 40
        # 面板可用文字宽度（左右留白，右端避开滚动条位）
        quest_wrap = QST_W - 18 - 30
        for qid in active:
            d = quests.defs.get(qid)
            if d is None:
                continue
            # 任务名（含标记，先脱标签再折行）
            name_lines = self._wrap_text(d.name, quest_wrap, fs)
            if ty + QST_ROW_H * 3 > y + QST_H - 10:
                break
            for ln in name_lines:
                surface.blit(fs.render(ln, True, (60, 52, 44)), (x + 18, ty))
                ty += 20
            # 目标 NPC（优先交付 NPC，无则用接取 NPC）
            npc_id = d.end_npc if d.end_npc is not None else d.start_npc
            if npc_id is not None:
                npc_txt = fs.render(
                    f"目标 NPC：{self.svc.assets.npc_name(str(npc_id))}",
                    True, (140, 110, 60))
                surface.blit(npc_txt, (x + 30, ty))
                ty += 16
            # 目标行
            if self.svc.quest_goal_lines is not None:
                for line in self.svc.quest_goal_lines(qid):
                    for ln in self._wrap_text(line, quest_wrap, fs):
                        if ty > y + QST_H - 12:
                            break
                        surface.blit(fs.render(ln, True, (90, 82, 70)),
                                     (x + 30, ty))
                        ty += 16
            ty += 8
