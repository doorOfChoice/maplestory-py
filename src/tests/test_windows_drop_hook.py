"""跨窗拖拽投递：非物品类 DragPickup 松手时投递给落点窗口的 handle_drop。

指令 / 技能这类「拖到目标」的载荷不该扔地，由 WindowManager 在松开瞬间
找落点窗口调用 handle_drop；物品链路行为保持不变（现有扔地用例覆盖）。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.render.windows.core.window import DragPickup, Window
from tests.windows_harness import draw_once, make_manager, make_services, \
    motion, press, release


class SourceWindow(Window):
    """一个可拖行：press 起点在行内即产出 kind=cmd 的 DragPickup。"""

    key = "src"

    def __init__(self, svc) -> None:
        super().__init__(svc)
        self.row = pygame.Rect(0, 0, 0, 0)

    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (10, 10)

    def pickup(self, pos) -> Optional[DragPickup]:
        if self.row.collidepoint(pos):
            return DragPickup(source=("cmd",), item=None, home=self.row,
                              kind="cmd", payload="attack", label="普通攻击")
        return None

    def draw(self, surface) -> None:
        x, y = self.place(surface, (180, 100))
        self.row = pygame.Rect(x + 4, y + 24, 170, 18)


class TargetWindow(Window):
    """一个投递目标：登记键格，handle_drop 命中键格才消费。"""

    key = "dst"

    def __init__(self, svc) -> None:
        super().__init__(svc)
        self.cell = pygame.Rect(0, 0, 0, 0)
        self.drops: List[Tuple[str, tuple]] = []

    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (400, 10)

    def handle_drop(self, pk: DragPickup, pos: Tuple[int, int]) -> bool:
        if self.cell.collidepoint(pos):
            self.drops.append((pk.payload, pos))
            return True
        return False

    def draw(self, surface) -> None:
        x, y = self.place(surface, (180, 100))
        self.cell = pygame.Rect(x + 4, y + 24, 40, 24)


def build() -> tuple:
    src, dst = SourceWindow(make_services()), TargetWindow(make_services())
    mgr = make_manager(src, dst)
    src.open()
    dst.open()
    draw_once(mgr)
    return mgr, src, dst


def test_drag_cmd_released_on_target_cell_delivers_payload():
    mgr, src, dst = build()
    assert press(mgr, src.row.center)
    assert motion(mgr, (dst.cell.left + 50, dst.cell.y - 100))
    assert release(mgr, dst.cell.center)
    assert dst.drops == [("attack", dst.cell.center)]
    assert mgr.take_dropped() is None       # 非物品绝不进扔地链路


def test_drag_cmd_released_off_target_is_noop():
    mgr, src, dst = build()
    assert press(mgr, src.row.center)
    assert motion(mgr, (dst.cell.bottom + 100, dst.cell.bottom + 100))
    assert release(mgr, (dst.cell.centerx, dst.cell.centery + 80))
    assert dst.drops == []
    assert mgr.take_dropped() is None


def test_default_handle_drop_returns_false():
    win = SourceWindow(make_services())
    pk = DragPickup(source=(), item=None, home=pygame.Rect(0, 0, 1, 1),
                    kind="cmd", payload="x", label="x")
    assert not win.handle_drop(pk, (0, 0))


# ── 物品拖拽：先问落点窗口，再接扔地链路 ───────────────────────────
class ItemSourceWindow(SourceWindow):
    """拖物品起点的源窗：记录 take_for_drop 是否被调用（扔地才调）。"""

    key = "isrc"

    def __init__(self, svc) -> None:
        super().__init__(svc)
        self.taken = 0

    def pickup(self, pos):
        if self.row.collidepoint(pos):
            return DragPickup(source=("cell",), item=object(), home=self.row)
        return None

    def take_for_drop(self, pk):
        self.taken += 1
        return pk.item


def build_item() -> tuple:
    src = ItemSourceWindow(make_services())
    dst = TargetWindow(make_services())
    mgr = make_manager(src, dst)
    src.open()
    dst.open()
    draw_once(mgr)
    return mgr, src, dst


def test_item_released_on_accepting_target_skips_ground():
    """物品落在愿收的窗口热区：handle_drop 消费，不取出、不扔地。"""
    mgr, src, dst = build_item()
    assert press(mgr, src.row.center)
    assert motion(mgr, dst.cell.center)
    assert release(mgr, dst.cell.center)
    assert len(dst.drops) == 1
    assert src.taken == 0
    assert mgr.take_dropped() is None


def test_item_released_unaccepted_still_drops_to_ground():
    """没人接住的物品拖拽：照旧走扔地链路。"""
    mgr, src, dst = build_item()
    assert press(mgr, src.row.center)
    assert motion(mgr, (10, 400))
    assert release(mgr, (10, 400))
    assert dst.drops == []
    assert src.taken == 1
    assert mgr.take_dropped() is not None
