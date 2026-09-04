"""GameContext：应用层组合根 —— 唯一知道「怎么 new」并完成接线的地方。

Game 主循环只消费这些已装配好的服务；新增子系统（如新的面板/系统）只需在
``create`` 里补一行注入，主循环与各组件互不感知彼此构造细节，便于测试与替换。

面板体系为 windows 子包：WindowServices 注入共享依赖（惰性玩家 / combat /
按键表 / 任务目标行回调），WindowManager 注册全部窗口并统一分发事件。
"""

from __future__ import annotations

from dataclasses import dataclass

from game.render.assets import Assets
from game.render.audio import Audio
from game.render.ui import UI
from game.render.windows import WindowManager, WindowServices
from game.render.windows.inventory import EquipWindow, InventoryWindow
from game.render.windows.keyconfig import KeyConfigWindow
from game.render.windows.questlog import QuestLogWindow
from game.render.windows.shop import ShopWindow
from game.render.windows.skill import SkillWindow
from game.render.windows.stat import StatWindow
from game.render.windows.storage import StorageWindow
from game.world import World


@dataclass
class GameContext:
    """装配完成的应用层依赖。全部由 ``create`` 组装，Game 只读写。"""

    assets: Assets
    world: World
    audio: Audio
    ui: UI
    windows: WindowManager

    @classmethod
    def create(cls, assets: Assets, quest_defs, save_data) -> "GameContext":
        """组装并接线：音效 / UI / 单图场景（World）/ 全部交互窗口。

        注：任务目标行回调（``svc.quest_goal_lines``）与全局按键表
        （``svc.bindings``）由 Game 在拿到本容器后注入，因其逻辑归属 Game
        的任务流程与本地配置，而非本工厂。
        """
        audio = Audio(assets, assets.map_bgm_path())
        ui = UI(assets)
        world = World(assets, quest_defs, save_data)
        svc = WindowServices(assets=assets, ui=ui,
                             player=lambda: world.player,
                             combat=world.combat)
        windows = WindowManager(svc)
        for win in (InventoryWindow(svc), EquipWindow(svc),
                    SkillWindow(svc), QuestLogWindow(svc), StatWindow(svc),
                    KeyConfigWindow(svc), ShopWindow(svc), StorageWindow(svc)):
            windows.add(win)
        return cls(assets=assets, world=world, audio=audio, ui=ui,
                   windows=windows)
