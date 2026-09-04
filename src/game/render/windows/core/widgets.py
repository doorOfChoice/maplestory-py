"""窗口共享小件：WZ 三态按钮 / Tooltip / Toast / 像素数字 / 滚动列表 / 图标适配。

素材路径约定同 panels：UIWindow.img 下 `<prefix>/{normal,mouseOver,pressed}/0`；
任何素材缺失返回 None，由调用方走 fallback 自绘。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.render.windows.core.services import WindowServices


# ── 素材与按钮 ─────────────────────────────────────────────────────
def wz_surface(svc: WindowServices, path: str,
               img: str = "UIWindow.img") -> Optional[pygame.Surface]:
    """UIWindow.img 取图（tuple 首帧 → Surface），缺失 None。"""
    hit = svc.assets.ui_surface(img, path)
    return hit[0] if hit else None


def ui_button_surface(svc: WindowServices, prefix: str, rect: pygame.Rect,
                      mouse: Tuple[int, int], pressed: bool = False,
                      img: str = "UIWindow.img") -> Optional[pygame.Surface]:
    """WZ 三态按钮图：pressed > mouseOver > normal；素材缺失返回 None。"""
    state = ("pressed" if pressed
             else "mouseOver" if rect.collidepoint(mouse) else "normal")
    return wz_surface(svc, f"{prefix}/{state}/0", img=img)


def fit_icon(icon: pygame.Surface, size: int) -> pygame.Surface:
    """图标等比缩进 size×size 框（不放大）。"""
    if icon.get_width() > size or icon.get_height() > size:
        return pygame.transform.scale(icon, (size, size))
    return icon


def ellipsize(text: str, font: pygame.font.Font, max_w: int) -> str:
    """把文字用省略号截断到 max_w 宽度内，确保不溢出控件边界。"""
    if font.size(text)[0] <= max_w:
        return text
    ell = "..."
    while text and font.size(text + ell)[0] > max_w:
        text = text[:-1]
    return text + ell


# ── 滚动列表状态 ───────────────────────────────────────────────────
class ScrollList:
    """一屏窗口列表的滚动状态：offset 为首条目索引，step 为滚轮一格步进条数。"""

    def __init__(self, step: int = 1) -> None:
        self.offset = 0
        self.step = step

    def clamp(self, total: int, visible: int) -> None:
        self.offset = max(0, min(max(0, total - visible), self.offset))

    def scroll(self, amount: int, total: int, visible: int) -> None:
        self.clamp(total, visible)
        self.offset = max(0, min(max(0, total - visible),
                                 self.offset + amount * self.step))

    def reset(self) -> None:
        self.offset = 0


# ── 官方深色菜单底（ContextMenu t/c/s 三段）────────────────────────
def draw_menu_bg(surface, svc: WindowServices, rect: pygame.Rect) -> bool:
    """UIWindow/ContextMenu 三段拼出任意高度深色底；素材缺失返回 False。"""
    t = wz_surface(svc, "ContextMenu/t")
    c = wz_surface(svc, "ContextMenu/c")
    s = wz_surface(svc, "ContextMenu/s")
    if not (t and c and s):
        return False
    W, H = rect.size
    th, sh = t.get_height(), s.get_height()
    top = t if W == t.get_width() else pygame.transform.smoothscale(t, (W, th))
    bot = s if W == s.get_width() else pygame.transform.smoothscale(s, (W, sh))
    surface.blit(top, rect.topleft)
    surface.blit(bot, (rect.x, rect.bottom - sh))
    mid_h = max(0, H - th - sh)
    if mid_h > 0:
        surface.blit(pygame.transform.smoothscale(c, (W, mid_h)),
                     (rect.x, rect.y + th))
    return True


def panel_frame(surface, rect: pygame.Rect,
                border=(90, 96, 110)) -> None:
    """fallback 自绘面板底（素材缺失时用）。"""
    pygame.draw.rect(surface, (18, 22, 30, 216), rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 1, border_radius=8)


# ── Tooltip / Toast ────────────────────────────────────────────────
def draw_tooltip(surface, svc: WindowServices, mouse_pos: Tuple[int, int],
                 text: str) -> None:
    """鼠标旁官方深色 Tooltip：首行标题（font），其余正文（font_small）。"""
    fs, f = svc.ui.font_small, svc.ui.font
    lines = text.split("\n")
    text_pad = 9
    inner = max(f.size(lines[0])[0],
                max((fs.size(l)[0] for l in lines[1:]), default=0))
    avail_w = min(inner + text_pad * 2, surface.get_width() - 20)
    x = min(mouse_pos[0] + 14, surface.get_width() - avail_w - 20)
    y = mouse_pos[1] + 14
    rect = pygame.Rect(x, y, avail_w, 26 + 16 + 8)
    if rect.bottom > surface.get_height():
        rect.bottom = surface.get_height()
    body_w = rect.w - text_pad * 2
    wrapped = [svc.ui._wrap(lines[0], body_w, f)]
    for ln in lines[1:]:
        wrapped.append(svc.ui._wrap(ln, body_w, fs))
    n_lines = sum(len(l) for l in wrapped)
    rect.h = 26 + (n_lines - 1) * 16 + 8
    if not draw_menu_bg(surface, svc, rect):
        panel_frame(surface, rect, (120, 126, 140))
    surface.blit(f.render(wrapped[0][0], True, (245, 220, 140)),
                 (rect.x + text_pad, rect.y + 5))
    ty = rect.y + 27
    for group in wrapped[1:]:
        for ln in group:
            surface.blit(fs.render(ln, True, (215, 220, 230)),
                         (rect.x + text_pad, ty))
            ty += 16


def draw_toast(surface, svc: WindowServices, text: str) -> None:
    """顶部居中短暂提示（如无法穿戴 / 背包已满）。"""
    f = svc.ui.font
    txt = f.render(text, True, (255, 230, 150))
    w, h = txt.get_width() + 20, 24
    x = (surface.get_width() - w) // 2
    plate = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 16, 10, 200), (0, 0, w, h), border_radius=6)
    pygame.draw.rect(plate, (150, 130, 90), (0, 0, w, h), 1, border_radius=6)
    plate.blit(txt, (10, (h - txt.get_height()) // 2))
    surface.blit(plate, (x, 34))


# ── 原版像素数字（StatusBar/number，白字染色）──────────────────────
class PixelNumbers:
    """数字串的原版像素字体绘制：白 glyph × 染色缓存；不可绘时回退文本。"""

    def __init__(self, svc: WindowServices) -> None:
        self.svc = svc
        self._cache: dict = {}

    def glyph(self, ch: str, color: Tuple[int, int, int]
              ) -> Optional[pygame.Surface]:
        key = (ch, color)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        path = "number/slash" if ch == "/" else f"number/{ch}"
        src = wz_surface(self.svc, path, img="StatusBar.img")
        if src is None:
            return None
        tinted = src.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self._cache[key] = tinted
        return tinted

    def width(self, text: str, color: Tuple[int, int, int]) -> Optional[int]:
        """像素数字串总宽；含不可绘制字符时 None（调用方回退字体）。"""
        w = 0
        for ch in text:
            img = self.glyph(ch, color) if (ch.isdigit() or ch == "/") else None
            if img is None:
                return None
            w += img.get_width() + 1
        return w

    def draw(self, surface, text: str, x: int, y_mid: int,
             color: Tuple[int, int, int] = (60, 60, 60)) -> Optional[int]:
        """绘制一串数字（垂直居中于 y_mid），返回结束 x；不可绘返回 None。"""
        if self.width(text, color) is None:
            return None
        for ch in text:
            img = self.glyph(ch, color)
            surface.blit(img, (x, y_mid - img.get_height() // 2))
            x += img.get_width() + 1
        return x
