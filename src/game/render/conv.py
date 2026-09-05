"""ConvPanel 会话面板：UtilDlgEx 白纸窗体 + 黑正文行 + 蓝字链接行 + yes/no/ok 按钮。

NPC 对话/任务选择/系统确认的统一渲染组件。单例、非模态：不注册进
WindowManager，会话打开时由 npc_dialogue 先于一切窗口消费点击。
坐标约定：全部为内部视口（VIEW_W×VIEW_H）坐标，面板水平居中、
底部悬在状态栏上方。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import pygame

from game import settings
from game.core.fonts import load_cjk_font
from game.core.markup import (IconSeg, Segment, TextSeg, final_color, split_colors,
                              split_item_icons)

# UtilDlgEx 内嵌窗体几何
DLG_W = 529            # it/ic/is 原生宽度
DLG_TOP_H = 28         # it 高
DLG_BOTTOM_H = 58      # is 高（底部蓝色页脚放按钮）
DLG_TEXT_X = 32        # 白纸左缘内缩
DLG_TEXT_W = 348       # 白纸内文字换行宽度
DLG_LINE_H = 20
DLG_TEXT_BASE = (60, 52, 44)   # 富文本无色段基色（会话面板/任务窗详情共用）

# 会话面板：黑正文行与蓝字链接行共存于同一 UtilDlgEx 白纸面板
LIST_ROW_H = 26
LIST_PAD_TOP = 12
LIST_PAD_BOTTOM = 10
CONV_TEXT_LINK_GAP = 6     # 黑文本与蓝字同时存在时的节间空隙
MAX_BODY_H = 340           # 正文视口最高：内容超限即封顶并滚轮滚动，不再撑开面板
WHEEL_STEP = LIST_ROW_H    # 滚轮每格滚动像素
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


def wrap_segments(text: str, width: int, font: pygame.font.Font,
                  icon_width: Optional[Callable[[int], int]] = None,
                  ) -> List[List[Segment]]:
    """带 #r/#g/#b/#d/#k 颜色码的文本按像素宽折行 → 每行 Segment 列表。

    TextSeg.color None = 基色；同色相邻文本片段合并，渲染层逐段 blit。
    传入 icon_width 时 #c<id># 切成 IconSeg（按该回调计宽参与折行）；
    不传则图标码保留原文，维持会话面板旧画法。文本内 \n 强制分行。
    """
    lines: List[List[Segment]] = []
    cur: List[Segment] = []
    cur_w = 0

    def flush() -> None:
        nonlocal cur, cur_w
        lines.append(cur)
        cur = []
        cur_w = 0

    state: Optional[Tuple[int, int, int]] = None
    for kind, val in split_item_icons(text) if icon_width else [("t", text)]:
        if kind == "i":
            assert icon_width is not None
            w = icon_width(int(val))
            if cur and cur_w + w > width:
                flush()
            cur.append(IconSeg(int(val)))
            cur_w += w
            continue
        segs = split_colors(val, state)
        state = final_color(val, state)
        for seg_text, color in segs:
            for ch in seg_text:
                if ch == "\n":
                    flush()
                    continue
                w = font.size(ch)[0]
                if cur and cur_w + w > width:
                    flush()
                if cur and isinstance(cur[-1], TextSeg) and cur[-1].color == color:
                    cur[-1].text += ch
                else:
                    cur.append(TextSeg(ch, color))
                cur_w += w
    if cur or not lines:
        lines.append(cur)
    return lines


# ── UI.wz / UtilDlgEx 单源小件（会话面板与 UI 回退窗共用）────────────

STATUS_BAR_FALLBACK_H = 71     # StatusBar 素材缺失时的回退高度


def ui_image(assets, img: str, path: str) -> Optional[pygame.Surface]:
    """取 UI.wz 图：assets.ui_surface 元组的首图，缺失 None。"""
    hit = assets.ui_surface(img, path)
    return hit[0] if hit else None


def status_bar_height(assets) -> int:
    bar = ui_image(assets, "StatusBar.img", "base/backgrnd")
    return bar.get_height() if bar is not None else STATUS_BAR_FALLBACK_H


def draw_dlg_frame(surface, assets, x: int, y: int, w: int, content_h: int) -> None:
    """画 UtilDlgEx 窗体：顶 it + 平铺 ic + 底 is。"""
    t = ui_image(assets, "UIWindow.img", "UtilDlgEx/it")
    c = ui_image(assets, "UIWindow.img", "UtilDlgEx/ic")
    s = ui_image(assets, "UIWindow.img", "UtilDlgEx/is")
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


def resolve_item_icons(text: str, item_icon, item_name) -> str:
    """预解析 #c 图标码的可用性：可出图保留码原样，缺素材回退物品名/#id。

    会话面板与任务窗详情共用，保证同一物品码在两处回退行为一致。
    """
    parts: List[str] = []
    for kind, val in split_item_icons(text or ""):
        if kind == "t":
            parts.append(val)
        elif item_icon(str(val)) is not None:
            parts.append(f"#c{int(val)}#")
        else:
            parts.append(item_name(str(val)) or f"#{val}")
    return "".join(parts)


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
        self.npc_id: Optional[str] = None                   # 锚定 NPC（右侧立绘）
        self.rect: Optional[pygame.Rect] = None
        # 正文滚动：scroll 为像素偏移，body_rect 为上一帧登记的视口
        self.scroll = 0
        self._max_scroll = 0
        self.body_rect: Optional[pygame.Rect] = None
        # 上一帧登记的热区，供下一帧命中判断
        self.buttons: List[Tuple[pygame.Rect, str]] = []    # (rect, key)
        self.entry_rects: List[Tuple[pygame.Rect, int]] = []
        self._icon_cache: dict = {}

    # ── 状态装载 ────────────────────────────────────────────────────
    def show(self, title: str, lines: List[str],
             links: List[Tuple[str, int]], buttons: List[str],
             terminal: bool, npc_id: Optional[str] = None) -> None:
        """buttons 为 ["yes","no"] 子集；terminal 时画 BtOK；npc_id 锚定右侧立绘。"""
        self.visible = True
        self.title = title
        self.lines = list(lines)
        self.links = list(links)
        self.button_keys = [b for b in buttons if b in ("yes", "no")]
        self.terminal = terminal
        self.npc_id = npc_id
        self.buttons = []
        self.entry_rects = []
        self.scroll = 0

    def hide(self) -> None:
        self.visible = False
        self.title = ""
        self.lines = []
        self.links = []
        self.button_keys = []
        self.terminal = False
        self.npc_id = None
        self.rect = None
        self.buttons = []
        self.entry_rects = []
        self.body_rect = None
        self.scroll = 0
        self._max_scroll = 0

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

    def handle_wheel(self, pos, amount: int) -> bool:
        """正文视口内滚轮滚动内容（amount：+1 下滚 / -1 上滚）；消费返回 True。"""
        if not self.visible or self.body_rect is None:
            return False
        if not self.body_rect.collidepoint(pos):
            return False
        self.scroll = max(0, min(self._max_scroll,
                                 self.scroll + amount * WHEEL_STEP))
        return True

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

    # ── 素材与绘制小件（转发模块级单源）────────────────────────────────
    def _img(self, img: str, path: str) -> Optional[pygame.Surface]:
        return ui_image(self.assets, img, path)

    def _status_bar_h(self) -> int:
        return status_bar_height(self.assets)

    def _dlg_frame(self, surface, x: int, y: int, w: int, content_h: int) -> None:
        draw_dlg_frame(surface, self.assets, x, y, w, content_h)

    # ── 物品内联图标 ─────────────────────────────────────────────────
    def _icon_surf(self, iid: str) -> Optional[pygame.Surface]:
        getter = getattr(self.assets, "item_icon", None)
        if getter is None:
            return None
        if iid not in self._icon_cache:
            self._icon_cache[iid] = getter(iid)
        return self._icon_cache[iid]

    def _icon_width(self, iid: int) -> int:
        surf = self._icon_surf(str(iid))
        return surf.get_width() if surf is not None else 0

    # ── NPC 立绘（右侧米色空区，画法与任务日志详情窗一致）─────────────
    def _draw_npc_portrait(self, surface, x: int, y: int, w: int,
                           body_h: int) -> None:
        if not self.npc_id:
            return
        getter = getattr(self.assets, "npc_frames", None)
        if getter is None:
            return
        try:
            frames = getter(str(self.npc_id), "stand")
        except Exception:
            return
        if not frames:
            return
        img = frames[0][0]
        left = x + DLG_TEXT_W + 2 * DLG_TEXT_X + 4
        box_w = max(0, x + w - 18 - left)        # 右缘避开滚动条细条
        box_h = max(0, body_h - 8)
        if box_w <= 0 or img.get_width() <= 0 or img.get_height() <= 0:
            return
        scale = min(1.0, box_w / img.get_width(), box_h / img.get_height())
        if scale < 1.0:
            img = pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * scale)),
                      max(1, int(img.get_height() * scale))))
        surface.blit(img, (left + (box_w - img.get_width()) // 2,
                           y + DLG_TOP_H + (body_h - img.get_height()) // 2))

    # ── 绘制（单一渲染路径）──────────────────────────────────────────
    def draw(self, surface) -> None:
        if not self.visible:
            return
        vw, vh = surface.get_width(), surface.get_height()
        # 正文先折行成素表面行（图标底对齐、行高取元素最大但不低于 DLG_LINE_H）
        text_rows: List[Tuple[List[Tuple[pygame.Surface, int]], int]] = []
        for ln in self.lines:
            prepared = resolve_item_icons(ln, self._icon_surf, self.assets.item_name)
            for line in wrap_segments(prepared, DLG_TEXT_W, self.font,
                                      self._icon_width):
                elems: List[Tuple[pygame.Surface, int]] = []
                line_h = DLG_LINE_H
                for seg in line:
                    if isinstance(seg, IconSeg):
                        surf = self._icon_surf(str(seg.item_id))
                        if surf is None:
                            continue
                        gap = 2
                    else:
                        surf = self.font.render(seg.text, True,
                                                seg.color or DLG_TEXT_BASE)
                        gap = 0
                    line_h = max(line_h, surf.get_height())
                    elems.append((surf, gap))
                text_rows.append((elems, line_h))
        has_links = bool(self.links)
        text_h = sum(h for _, h in text_rows)
        link_block = len(self.links) * LIST_ROW_H
        if text_rows and has_links:
            link_block += CONV_TEXT_LINK_GAP
        content_h = max(70, LIST_PAD_TOP + text_h + link_block + LIST_PAD_BOTTOM)
        body_h = min(content_h, MAX_BODY_H)
        self._max_scroll = max(0, content_h - body_h)
        self.scroll = max(0, min(self.scroll, self._max_scroll))
        h = DLG_TOP_H + body_h + DLG_BOTTOM_H
        w = DLG_W
        x = (vw - w) // 2
        y = vh - self._status_bar_h() - 8 - h
        self.rect = pygame.Rect(x, y, w, h)
        self._dlg_frame(surface, x, y, w, body_h)
        self.body_rect = pygame.Rect(x, y + DLG_TOP_H, w, body_h)

        # 正文整体先画进 scratch（内容坐标系），再按滚动偏移贴出视口窗口：
        # 超限内容不撑高面板，改为视口内滚动。
        scratch = pygame.Surface((w, content_h), pygame.SRCALPHA)
        # 黑正文行：逐段着色（颜色码/实体名高亮），None = 基色
        ty = LIST_PAD_TOP
        for elems, line_h in text_rows:
            tx = DLG_TEXT_X
            for surf, gap in elems:
                scratch.blit(surf, (tx, ty + line_h - surf.get_height()))
                tx += surf.get_width() + gap
            ty += line_h

        # 蓝字链接行：起点在黑文本之后，悬停高亮与 Lv 灰标注沿用列表画法；
        # 热区只登记视口内（含部分可见）的行，索引保持全列表序号
        self.entry_rects = []
        if has_links:
            gap = CONV_TEXT_LINK_GAP if text_rows else 0
            mx, my = pygame.mouse.get_pos()
            hx = mx * settings.VIEW_W // settings.WINDOW_W
            hy = my * settings.VIEW_H // settings.WINDOW_H
            link_rows = self.row_rects(x, text_h + gap - DLG_TOP_H,
                                       DLG_TEXT_W + 2 * DLG_TEXT_X,
                                       len(self.links))
            for i, ((rx, cy, rw, rh), (label, note)) in enumerate(
                    zip(link_rows, self.links)):
                rect = pygame.Rect(rx, y + DLG_TOP_H + cy - self.scroll, rw, rh)
                vis = rect.clip(self.body_rect)
                if vis.height <= 0:
                    continue
                self.entry_rects.append((vis, i))
                hovered = vis.collidepoint(hx, hy)
                lx = rx - x          # scratch 为面板局部坐标，须剥掉面板绝对偏移
                if hovered:
                    hl = pygame.Surface((rw, rh), pygame.SRCALPHA)
                    pygame.draw.rect(hl, (150, 190, 250, 70), (0, 0, rw, rh),
                                     border_radius=6)
                    scratch.blit(hl, (lx, cy))
                base = QUEST_LIST_BLUE_HOVER if hovered else QUEST_LIST_BLUE
                tx = lx + 6
                for seg, color in split_colors(label):
                    t = self.font.render(seg, True, color or base)
                    scratch.blit(t, (tx, cy + (rh - t.get_height()) // 2))
                    tx += t.get_width()
                if note:
                    lv = self.font_small.render(f"Lv {note}", True, (150, 140, 128))
                    scratch.blit(lv, (lx + rw - lv.get_width() - 6,
                                      cy + (rh - lv.get_height()) // 2))

        surface.blit(scratch, (x, y + DLG_TOP_H),
                     pygame.Rect(0, self.scroll, w,
                                 min(body_h, content_h - self.scroll)))

        # NPC 立绘：右侧米色空区，上下居中、随面板固定不随正文滚动
        self._draw_npc_portrait(surface, x, y, w, body_h)

        # 滚动条：内容超出视口时在白纸右缘画细条（与任务日志窗同款画法）
        if self._max_scroll > 0:
            track = pygame.Rect(x + w - 14, y + DLG_TOP_H + 6, 5, body_h - 12)
            n = max(12, body_h * body_h // content_h)
            thumb = pygame.Rect(track.x,
                                track.y + (track.height - n) * self.scroll
                                // self._max_scroll,
                                track.width, min(n, track.height))
            pygame.draw.rect(surface, (176, 186, 198), track, border_radius=2)
            pygame.draw.rect(surface, (110, 122, 140), thumb, border_radius=2)

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
