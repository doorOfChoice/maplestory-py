"""windows 子包：组件化的交互面板（Window + WindowManager + 共享 widgets）。"""

from __future__ import annotations

from game.render.windows.core.manager import WindowManager, to_view_pos
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DragPickup, Window

__all__ = ["Window", "WindowManager", "WindowServices", "DragPickup",
           "to_view_pos"]
