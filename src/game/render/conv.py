"""ConvPanel 会话面板：UtilDlgEx 白纸窗体 + 黑正文行 + 蓝字链接行 + yes/no/ok 按钮。

NPC 对话/任务选择/系统确认的统一渲染组件。单例、非模态：不注册进
WindowManager，会话打开时由 npc_dialogue 先于一切窗口消费点击。
坐标约定：全部为内部视口（VIEW_W×VIEW_H）坐标，面板水平居中、
底部悬在状态栏上方。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game import settings
from game.core.fonts import load_cjk_font
from game.core.markup import split_colors

# UtilDlgEx 内嵌窗体几何
DLG_W = 529            # it/ic/is 原生宽度
DLG_TOP_H = 28         # it 高
DLG_BOTTOM_H = 58      # is 高（底部蓝色页脚放按钮）
DLG_TEXT_X = 32        # 白纸左缘内缩
DLG_TEXT_W = 348       # 白纸内文字换行宽度
DLG_LINE_H = 20

# 会话面板：黑正文行与蓝字链接行共存于同一 UtilDlgEx 白纸面板
LIST_ROW_H = 26
LIST_PAD_TOP = 12
LIST_PAD_BOTTOM = 10
CONV_TEXT_LINK_GAP = 6     # 黑文本与蓝字同时存在时的节间空隙
QUEST_LIST_BLUE = (51, 102, 204)
QUEST_LIST_BLUE_HOVER = (120, 175, 250)


def wrap_text(text: str, width: int, font: pygame.font.Font) -> List[str]:
    """按像素宽逐字换行；空串返回 ['']。"""
    lines: List[str] = []
    cur = ""
    for ch in text:
        if cur and font.size(cur + ch)[0] > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines or [""]


def wrap_segments(text: str, width: int,
                  font: pygame.font.Font) -> List[List[Tuple[str, Optional[tuple]]]]:
    """带 #r/#g/#b/#d/#k 颜色码的文本按像素宽折行 → 每行 (片段, 颜色) 列表。

    颜色 None = 基色；同色相邻片段合并，渲染层逐段 blit。
    """
    lines: List[List[Tuple[str, Optional[tuple]]]] = []
    cur: List[Tuple[str, Optional[tuple]]] = []
    cur_w = 0
    for seg_text, color in split_colors(text):
        for ch in seg_text:
            w = font.size(ch)[0]
            if cur and cur_w + w > width:
                lines.append(cur)
                cur = []
                cur_w = 0
            if cur and cur[-1][1] == color:
                cur[-1] = (cur[-1][0] + ch, color)
            else:
                cur.append((ch, color))
            cur_w += w
    if cur or not lines:
        lines.append(cur)
    return lines


class ConvPanel:
    """统一会话面板：标题 + 黑正文行 + 蓝字链接行（(label, Lv 标注)）+ 按钮行。"""

    def __init__(self, assets) -> None:
        self.assets = assets
        self.font = load_cjk_font(11)
        self.font_big = load_cjk_font(14)
        self.font_small = load_cjk_font(10)
        self.visible = False
        self.title = ""
        self.lines: List[str] = []                          # 黑正文行（已解析标记）
        self.links: List[Tuple[str, int]] = []              # 蓝字 (标注, Lv)
        self.button_keys: List[str] = []                    # yes/no 子集
        self.terminal = False                               # 终态画 BtOK
        self.rect: Optional[pygame.Rect] = None
        # 上一帧登记的热区，供下一帧命中判断
        self.buttons: List[Tuple[pygame.Rect, str]] = []    # (rect, key)
        self.entry_rects: List[Tuple[pygame.Rect, int]] = []

    # ── 状态装载 ────────────────────────────────────────────────────
    def show(self, title: str, lines: List[str],
             links: List[Tuple[str, int]], buttons: List[str],
             terminal: bool) -> None:
        """buttons 为 ["yes","no"] 子集；terminal 时画 BtOK。"""
        self.visible = True
        self.title = title
        self.lines = list(lines)
        self.links = list(links)
        self.button_keys = [b for b in buttons if b in ("yes", "no")]
        self.terminal = terminal
        self.buttons = []
        self.entry_rects = []

    def hide(self) -> None:
        self.visible = False
        self.title = ""
        self.lines = []
        self.links = []
        self.button_keys = []
        self.terminal = False
        self.rect = None
        self.buttons = []
        self.entry_rects = []

    # ── 命中判断 ────────────────────────────────────────────────────
    def link_hit(self, pos) -> Optional[int]:
        """命中某条蓝字链接行 → 返回其序号；否则 None。"""
        if not self.visible:
            return None
        for rect, idx in self.entry_rects:
            if rect.collidepoint(pos):
                return idx
        return None

    def button_hit(self, pos) -> Optional[str]:
        """命中按钮 → 返回按钮键（yes/no/ok），否则 None。"""
        if not self.visible:
            return None
        for rect, key in self.buttons:
            if rect.collidepoint(pos):
                return key
        return None

    def panel_hit(self, pos) -> bool:
        return (self.visible and self.rect is not None
                and self.rect.collidepoint(pos))

    # ── 列表几何（纯函数，供测试）─────────────────────────────────────
    @staticmethod
    def list_body_height(n_rows: int) -> int:
        """列表正文高 = 顶部留白 + 行数×行高 + 底部留白（不小于最小值）。"""
        return max(70, LIST_PAD_TOP + n_rows * LIST_ROW_H + LIST_PAD_BOTTOM)

    @staticmethod
    def row_rects(x: int, y: int, w: int,
                  n_rows: int) -> List[Tuple[int, int, int, int]]:
        """各条目行 (x, y, w, h)：从顶栏下方留白起逐行等距，左右内缩避开边框。"""
        top = y + DLG_TOP_H + LIST_PAD_TOP
        return [(x + DLG_TEXT_X, top + i * LIST_ROW_H,
                 w - 2 * DLG_TEXT_X, LIST_ROW_H) for i in range(n_rows)]

    # ── 素材与绘制小件 ───────────────────────────────────────────────
    def _img(self, img: str, path: str) -> Optional[pygame.Surface]:
        hit = self.assets.ui_surface(img, path)
        return hit[0] if hit else None

    def _status_bar_h(self) -> int:
        bar = self._img("StatusBar.img", "base/backgrnd")
        return bar.get_height() if bar is not None else 71

    def _dlg_frame(self, surface, x: int, y: int, w: int, content_h: int) -> None:
        """画 UtilDlgEx 窗体：顶 it + 平铺 ic + 底 is。"""
        t = self._img("UIWindow.img", "UtilDlgEx/it")
        c = self._img("UIWindow.img", "UtilDlgEx/ic")
        s = self._img("UIWindow.img", "UtilDlgEx/is")
        if t is None or c is None or s is None:
            return
        if w != t.get_width():
            t = pygame.transform.smoothscale(t, (w, t.get_height()))
            c = pygame.transform.smoothscale(c, (w, c.get_height()))
            s = pygame.transform.smoothscale(s, (w, s.get_height()))
        surface.blit(t, (x, y))
        ny = y + t.get_height()
        remaining = max(0, content_h)
        while remaining > 0:
            hh = min(c.get_height(), remaining)
            surface.blit(c, (x, ny), pygame.Rect(0, 0, w, hh))
            ny += hh
            remaining -= hh
        surface.blit(s, (x, y + t.get_height() + content_h))

    # ── 绘制（单一渲染路径）──────────────────────────────────────────
    def draw(self, surface) -> None:
        if not self.visible:
            return
        vw, vh = surface.get_width(), surface.get_height()
        wrapped: List[List[Tuple[str, Optional[tuple]]]] = []
        for ln in self.lines:
            for part in ln.split("\n"):
                wrapped.extend(wrap_segments(part, DLG_TEXT_W, self.font))
        has_links = bool(self.links)
        text_h = len(wrapped) * DLG_LINE_H
        link_block = len(self.links) * LIST_ROW_H
        if wrapped and has_links:
            link_block += CONV_TEXT_LINK_GAP
        body_h = max(70, LIST_PAD_TOP + text_h + link_block + LIST_PAD_BOTTOM)
        h = DLG_TOP_H + body_h + DLG_BOTTOM_H
        w = DLG_W
        x = (vw - w) // 2
        y = vh - self._status_bar_h() - 8 - h
        self.rect = pygame.Rect(x, y, w, h)
        self._dlg_frame(surface, x, y, w, body_h)

        # 标题（任务名/会话名，金色）
        # surface.blit(self.font_big.render(self.title, True, (255, 216, 96)),
        #              (x + DLG_TEXT_X, y + 7))
        # 黑正文行：逐段着色（颜色码/实体名高亮），None = 基色
        ty = y + DLG_TOP_H + LIST_PAD_TOP
        for segs in wrapped:
            tx = x + DLG_TEXT_X
            for seg, color in segs:
                t = self.font.render(seg, True, color or (60, 52, 44))
                surface.blit(t, (tx, ty))
                tx += t.get_width()
            ty += DLG_LINE_H

        # 蓝字链接行：起点在标题+黑文本之后，悬停高亮与 Lv 灰标注沿用列表画法
        self.entry_rects = []
        if has_links:
            gap = CONV_TEXT_LINK_GAP if wrapped else 0
            mx, my = pygame.mouse.get_pos()
            hx = mx * settings.VIEW_W // settings.WINDOW_W
            hy = my * settings.VIEW_H // settings.WINDOW_H
            rows = self.row_rects(x, y + text_h + gap,
                                  DLG_TEXT_W + 2 * DLG_TEXT_X, len(self.links))
            for i, ((rx, ry, rw, rh), (label, note)) in enumerate(zip(rows, self.links)):
                rect = pygame.Rect(rx, ry, rw, rh)
                self.entry_rects.append((rect, i))
                hovered = rect.collidepoint(hx, hy)
                if hovered:
                    hl = pygame.Surface((rw, rh), pygame.SRCALPHA)
                    pygame.draw.rect(hl, (150, 190, 250, 70), (0, 0, rw, rh),
                                     border_radius=6)
                    surface.blit(hl, (rx, ry))
                base = QUEST_LIST_BLUE_HOVER if hovered else QUEST_LIST_BLUE
                tx = rx + 6
                for seg, color in split_colors(label):
                    t = self.font.render(seg, True, color or base)
                    surface.blit(t, (tx, ry + (rh - t.get_height()) // 2))
                    tx += t.get_width()
                if note:
                    lv = self.font_small.render(f"Lv {note}", True, (150, 140, 128))
                    surface.blit(lv, (rx + rw - lv.get_width() - 6,
                                      ry + (rh - lv.get_height()) // 2))

        # 按钮行：先画的在最右（右起叠放），ok 由终态追加
        keys = list(self.button_keys) + (["ok"] if self.terminal else [])
        btns: List[Tuple[pygame.Rect, str]] = []
        right = x + w - 14
        for key in reversed(keys):
            img_name = {"yes": "BtYes", "no": "BtNo", "ok": "BtOK"}.get(key)
            img = self._img("UIWindow.img", f"UtilDlgEx/{img_name}/normal/0")
            if img is None:
                continue
            bw_, bh_ = img.get_width(), img.get_height()
            bx = right - bw_
            by = y + h - bh_ - 14
            surface.blit(img, (bx, by))
            btns.append((pygame.Rect(bx, by, bw_, bh_), key))
            right -= bw_ + 10
        self.buttons = btns
