"""windows 子包测试 harness：假 UI/Assets、事件助手与 manager 装配。

所有面板测试共用：不依赖 WZ 素材（ui_surface 恒 None → 全走 fallback），
事件助手直接构造 pygame.Event 走公开 dispatch 接口。
"""

from __future__ import annotations

import os
from typing import List, Optional

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

pygame.init()

from game.render.windows.core.manager import WindowManager  # noqa: E402
from game.render.windows.core.services import WindowServices  # noqa: E402
from game.render.windows.core.window import Window  # noqa: E402


class FakeUI:
    """只提供字体与折行，绘制路径不触碰 WZ。"""

    def __init__(self) -> None:
        self.font = pygame.font.Font(None, 14)
        self.font_small = pygame.font.Font(None, 12)
        self.font_tiny = pygame.font.Font(None, 10)
        self.font_big = self.font

    @staticmethod
    def _wrap(text: str, width: int, font) -> List[str]:
        lines: List[str] = []
        cur = ""
        for ch in text:
            if cur and font.size(cur + ch)[0] > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
        return lines or [""]


class FakeAssets:
    """全部素材缺失：ui_surface 返回 None，图标/名字给空。"""

    def ui_surface(self, img: str, path: str):
        return None

    def item_icon(self, item_id: str):
        return None

    def equip_icon(self, item_id: str):
        return None

    def skill_icon(self, skill_id: str):
        return None

    def item_name(self, item_id: str) -> str:
        return ""

    def item_desc(self, item_id: str) -> str:
        return ""

    def mob_name_of(self, mob_id) -> str:
        return f"mob{mob_id}"

    def npc_name(self, npc_id) -> str:
        return f"npc{npc_id}"

    def map_name_of(self, map_id) -> str:
        return f"map{map_id}"


def make_services(player=None) -> WindowServices:
    return WindowServices(assets=FakeAssets(), ui=FakeUI(),
                          player=lambda: player)


def make_manager(*wins: Window) -> WindowManager:
    """装配 manager 并完成 svc 接线（同 GameContext.create 的语义）。"""
    svc = wins[0].svc if wins else make_services()
    mgr = WindowManager(svc)
    for win in wins:
        mgr.add(win)
    return mgr


class BoxWindow(Window):
    """行为测试用最小窗口：固定大小、可放一个热区按钮。"""

    def __init__(self, svc, key: str = "box", size=(100, 60), at=(10, 10),
                 chrome: bool = True):
        super().__init__(svc)
        self.key = key
        self._size = size
        self._at = at
        self._chrome = chrome
        self.buttons: List[tuple] = []      # (Rect, name)
        self.clicked: List[str] = []
        self.wheeled: List[int] = []
        self.picked: List[tuple] = []
        self.keys_seen: List[int] = []
        self.drag: Optional[tuple] = None   # 供 pickup 测试注入

    def anchor(self, vw: int, vh: int):
        return self._at

    def handle_mouse_down(self, pos) -> bool:
        for rect, name in self.buttons:
            if rect.collidepoint(pos):
                self.clicked.append(name)
                return True
        return False

    def handle_wheel(self, pos, amount: int) -> bool:
        self.wheeled.append(amount)
        return True

    def handle_right_click(self, pos) -> bool:
        self.clicked.append("right")
        return True

    def handle_keydown(self, key: int) -> bool:
        self.keys_seen.append(key)
        return True

    def pickup(self, pos):
        if self.drag is not None and self.rect.collidepoint(pos):
            src, item = self.drag
            from game.render.windows.core.window import DragPickup
            return DragPickup(source=src, item=item, home=self.rect)
        return None

    def draw(self, surface) -> None:
        x, y = self.place(surface, self._size)
        surface.fill((30, 30, 40), pygame.Rect(x, y, *self._size))
        if self._chrome:
            self.add_chrome(surface, x, y, self._size[0], 20)


def close_button_pos(win: Window) -> tuple:
    assert win.close_rect is not None, "窗口未绘制或无 chrome"
    return win.close_rect.center


# ── 事件助手（pos 为 VIEW 坐标，scale=1 时与窗口坐标一致）──────────
def _ev(type_, pos=None, button=None, key=None):
    attr = {}
    if pos is not None:
        attr["pos"] = pos
    if button is not None:
        attr["button"] = button
    if key is not None:
        attr["key"] = key
    return pygame.event.Event(type_, attr)


def press(mgr, pos, button=1):
    return mgr.dispatch(_ev(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))


def release(mgr, pos, button=1):
    return mgr.dispatch(_ev(pygame.MOUSEBUTTONUP, pos=pos, button=button))


def motion(mgr, pos):
    return mgr.dispatch(_ev(pygame.MOUSEMOTION, pos=pos))


def wheel(mgr, pos, up=True):
    return mgr.dispatch(_ev(pygame.MOUSEBUTTONDOWN, pos=pos,
                            button=4 if up else 5))


def key_press(mgr, key):
    return mgr.dispatch_key(key)


def draw_once(mgr, size=(800, 600)) -> pygame.Surface:
    surface = pygame.Surface(size, pygame.SRCALPHA)
    mgr.draw(surface)
    return surface
