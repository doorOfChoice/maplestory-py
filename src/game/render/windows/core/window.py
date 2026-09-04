"""Window 基类：可见窗口的公共契约 —— chrome / 定位 / 事件钩子。

事件模型（即时模式）：窗口在 draw() 中重建自己的热区列表，manager 依据
本帧登记的 rect / title_rect / close_rect 做下一帧命中分发；跨窗口关注点
（拖标题、拖物品、双击、tooltip、toast、z 序）全部上收 WindowManager。
坐标约定：事件 pos 均为内部视口（VIEW_W×VIEW_H）坐标。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import pygame

from game.render.windows.core import widgets
from game.render.windows.core.services import WindowServices

DRAG_THRESHOLD = 6.0       # 按下后移动超过该像素才判定为「拖出扔东西」
DOUBLE_CLICK_TIME = 0.35   # 双击使用/穿戴的两次点击最大间隔（秒）


@dataclass
class DragPickup:
    """一次「在窗口元素上按下并开始拖拽」的快照。

    kind="item" 走原扔地链路；其它 kind（cmd / skill 等）松手时投递给落点
    窗口的 handle_drop，payload / label 描述被拖内容。
    """

    source: tuple
    item: "object"
    home: pygame.Rect
    kind: str = "item"
    payload: "object" = None
    label: str = ""


class Window:
    """所有可开合面板的基类。子类实现 draw()，按需覆写事件钩子。"""

    key: str = ""
    escape_closes: bool = False        # Esc 优先关闭（按键设置 / 商店 / 仓库）
    closes_on_map_change: bool = False  # 切图自动关闭（NPC 绑定窗口）
    interactive: bool = True           # 常驻装饰类面板置 False：不置顶、不拦事件

    def __init__(self, svc: WindowServices) -> None:
        self.svc = svc
        self.visible = False
        self.rect = pygame.Rect(0, 0, 0, 0)      # 当前帧外框
        self.title_rect: Optional[pygame.Rect] = None   # 本帧标题热区（无 chrome 则 None）
        self.close_rect: Optional[pygame.Rect] = None   # 本帧关闭按钮热区
        self._user_pos: Optional[Tuple[int, int]] = None  # 用户拖拽后的位置
        self.numbers: Optional[widgets.PixelNumbers] = None

    # ── 开合 ───────────────────────────────────────────────────────
    def open(self) -> None:
        self.visible = True

    def close(self) -> None:
        self.visible = False
        self.on_close()

    def toggle(self) -> None:
        if self.visible:
            self.close()
        else:
            self.open()

    def on_close(self) -> None:
        """关窗时子类清理私有交互态（拖拽 / 录入 / 选中）。"""

    # ── 定位 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        """默认左上角（子类按窗口用途覆写）。"""
        return (8, 8)

    def place(self, surface, size: Tuple[int, int]) -> Tuple[int, int]:
        """绘制前调用：确定本帧位置（含拖拽记忆）并限幅，更新 self.rect。"""
        vw, vh = surface.get_width(), surface.get_height()
        x, y = self._user_pos if self._user_pos is not None else self.anchor(vw, vh)
        x = max(0, min(vw - size[0], int(x)))
        y = max(0, min(vh - size[1], int(y)))
        self.rect = pygame.Rect(x, y, size[0], size[1])
        return x, y

    def move_to(self, x: int, y: int, vw: int, vh: int) -> None:
        """manager 拖标题时调用：移动窗口并限幅在视口内。"""
        w, h = self.rect.size
        x = max(0, min(vw - w, int(x)))
        y = max(0, min(vh - h, int(y)))
        self._user_pos = (x, y)
        self.rect.topleft = (x, y)
        if self.title_rect is not None:
            self.title_rect.topleft = (x, y)
        if self.close_rect is not None:
            self.close_rect.topleft = (x + w - 34, y + 3)

    # ── chrome（标题拖拽热区 + 原版关闭钮）──────────────────────────
    def add_chrome(self, surface, x: int, y: int, w: int, title_h: int) -> None:
        """子类 blit 底板后调用：登记标题热区并画右上角关闭按钮。"""
        self.title_rect = pygame.Rect(x, y, w, title_h)
        rect = pygame.Rect(x + w - 34, y + 3, 32, 15)
        img = widgets.ui_button_surface(self.svc, "BtUIClose", rect,
                                        pygame.mouse.get_pos())
        if img is not None:
            surface.blit(img, rect.topleft)
        else:                       # 素材缺失 → 自绘红 × 小钮
            pygame.draw.rect(surface, (150, 52, 46), rect, border_radius=3)
            pygame.draw.line(surface, (255, 235, 235),
                             (rect.x + 11, rect.y + 4), (rect.x + 21, rect.y + 11), 2)
            pygame.draw.line(surface, (255, 235, 235),
                             (rect.x + 21, rect.y + 4), (rect.x + 11, rect.y + 11), 2)
        self.close_rect = rect

    # ── 事件钩子（子类按需覆写；返回 True = 已消费）─────────────────
    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        return False

    def handle_mouse_motion(self, pos: Tuple[int, int]) -> bool:
        """无全局拖拽时，manager 把命中本窗口的移动事件转给子类（滚动条拖拽等）。"""
        return False

    def handle_mouse_up(self, pos: Tuple[int, int]) -> bool:
        """无全局拖拽/拾取时，manager 把命中本窗口的松开事件转给子类。"""
        return False

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        return False

    def handle_right_click(self, pos: Tuple[int, int]) -> bool:
        return False

    def handle_keydown(self, key: int) -> bool:
        return False

    # ── 物品拖拽三态（背包系窗口实现，manager 驱动状态机）───────────
    def pickup(self, pos: Tuple[int, int]) -> Optional[DragPickup]:
        return None

    def handle_drop(self, pk: DragPickup, pos: Tuple[int, int]) -> bool:
        """松手时由 manager 投递（含物品）；返回 True = 已消费、不再扔地。"""
        return False

    def activate(self, pk: DragPickup) -> None:
        """双击来源格子：使用 / 穿戴 / 脱下。"""

    def take_for_drop(self, pk: DragPickup):
        """拖出来源窗口后松手：从容器取出该物品并返回。"""
        return None

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        raise NotImplementedError
