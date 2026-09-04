"""窗口服务依赖：由 GameContext 一次性装配、注入所有 Window。

窗口不感知 Game / World，只通过本容器取素材、字体与惰性玩家引用；
flash / tooltip 在接线前为空操作，接线后指向 WindowManager 的全局服务。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:
    from game.core.keybindings import KeyBindings
    from game.entities.player import Player
    from game.render.assets import Assets
    from game.render.ui import UI
    from game.systems.combat import Combat


def _noop(*_args) -> None:
    return None


@dataclass
class WindowServices:
    """所有窗口的共享依赖。player 用可调用惰性取（存档重建后仍是当前角色）。"""

    assets: "Assets"
    ui: "UI"
    player: Callable[[], "Player"]
    bindings: Optional["KeyBindings"] = None
    combat: Optional["Combat"] = None
    quest_goal_lines: Optional[Callable[[str], List[str]]] = None
    flash: Callable[..., None] = _noop
    tooltip: Callable[..., None] = _noop
