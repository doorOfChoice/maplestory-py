"""GameContext：应用层组合根 —— 唯一知道「怎么 new」并完成接线的地方。

Game 主循环只消费这些已装配好的服务；新增子系统（如新的面板/系统）只需在
``create`` 里补一行注入，主循环与各组件互不感知彼此构造细节，便于测试与替换。
"""

from __future__ import annotations

from dataclasses import dataclass

from game.render.assets import Assets
from game.render.audio import Audio
from game.render.panels import Panels
from game.render.shop_panel import ShopPanel
from game.render.storage_panel import StoragePanel
from game.render.ui import UI
from game.world import World


@dataclass
class GameContext:
    """装配完成的应用层依赖。全部由 ``create`` 组装，Game 只读写。"""

    assets: Assets
    world: World
    audio: Audio
    ui: UI
    panels: Panels
    shop_panel: ShopPanel
    storage_panel: StoragePanel

    @classmethod
    def create(cls, assets: Assets, quest_defs, save_data) -> "GameContext":
        """组装并接线：音效 / UI / 面板 / 单图场景（World）。

        注：panels 的任务目标行回调由 Game 在拿到本容器后注入
        （``ctx.panels._quest_goal_lines``），因其逻辑归属 Game 的
        任务流程，而非本工厂。
        """
        audio = Audio(assets, assets.map_bgm_path())
        ui = UI(assets)
        panels = Panels(ui, assets)
        world = World(assets, quest_defs, save_data)
        panels.combat = world.combat
        shop_panel = ShopPanel(ui, assets)
        storage_panel = StoragePanel(ui, assets)
        return cls(assets=assets, world=world, audio=audio, ui=ui,
                   panels=panels, shop_panel=shop_panel,
                   storage_panel=storage_panel)
