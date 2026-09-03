"""合成 Assets：在无 WZ 文件的环境下驱动 Game 的开屏→世界构建→更新/绘制。

用于游戏循环重构的 headless 冒烟护航：不依赖真实 WZ，也不使用 mock，
而是显式提供与真实 Assets 同名的查询方法（返回保守的空白帧/空表），
并以真实数据构造 foothold / portal / life，让物理与地图切换路径真正跑通。
"""

from __future__ import annotations

import types
from typing import Any, Dict, List

import pygame

pygame.init()


class FakeWzRoot:
    """WZ 根：images.get 一律返回 None，让任务的技能解析走「素材缺失」分支。"""

    def __init__(self) -> None:
        self.images: Dict[str, Any] = {}
        self.subdirs: Dict[str, Any] = {}

    def get(self, name: str):
        return None


class FakeWz:
    """WZ 档案：提供 .root（含 .images / .get），与真实 WzFile 接口一致。"""

    def __init__(self) -> None:
        self.root = FakeWzRoot()


class FakeAssets:
    """合成资产提供者。数据属性为真实值；视觉/信息查询返回保守空值。"""

    def __init__(self, map_id: str = "100010000", region: str = "EMS"):
        self.map_id = map_id
        self.region = region
        self.map_width = 1600
        self.map_height = 1000
        self.bounds = {"left": -800, "top": -500, "right": 800, "bottom": 500}
        self.footholds: List[Dict] = [{
            "id": 1, "layer": 0, "platform": 0,
            "x1": -800, "y1": 0, "x2": 800, "y2": 0, "prev": -1, "next": -1,
        }]
        self.ropes: List[Dict] = []
        self.portals: List[Dict] = [
            {"name": "sp", "type": 0, "x": 0.0, "y": 0.0, "targetMap": 0},
            {"name": "to2", "type": 2, "x": 300.0, "y": 0.0,
             "targetMap": "200000000", "targetName": "sp"},
        ]
        self.life: List[Dict] = [
            {"type": "mob", "id": "0100101", "x": -200, "y": 0, "cy": 0,
             "rx0": -500, "rx1": -100, "mobTime": 0},
            {"type": "npc", "id": "1012100", "x": 50, "y": 0, "cy": 0,
             "flip": False},
        ]
        self.map_renderer = types.SimpleNamespace(
            has_map=lambda mid: mid == "200000000")
        self.wz: Dict[str, Any] = {k: FakeWz() for k in (
            "Map", "Character", "Mob", "Npc", "String", "Sound", "UI",
            "Effect", "Skill", "Quest")}
        self._tile = pygame.Surface((16, 16))
        self.map_surface = pygame.Surface((self.map_width, self.map_height))
        self.minimap_base = pygame.Surface((self.map_width, self.map_height))
        self.back_layers: List = []

    # ── 地图描述 / 名字查询 ──────────────────────────────────────────
    @property
    def map_desc(self) -> Dict:
        return {"minimap": {}}

    def minimap_surface(self) -> pygame.Surface:
        return self._tile

    def map_bgm_path(self) -> None:
        return None

    def map_name(self) -> str:
        return "假地图"

    def map_banner(self) -> tuple:
        return ("假地图", "街道")

    def map_name_of(self, *a) -> str:
        return "假图"

    def npc_name(self, *a) -> str:
        return "假NPC"

    def mob_name_of(self, *a) -> str:
        return "假怪"

    def item_name(self, *a) -> str:
        return "假物品"

    def item_price(self, *a) -> int:
        return 0

    # ── 地图切换（is_load_done 恒真：加载立即完成）─────────────────
    @property
    def is_load_done(self) -> bool:
        return True

    def start_load_map(self, map_id: str) -> None:
        self.map_id = str(map_id)

    def finish_load_map(self) -> None:
        return None

    def preload_neighbors(self, targets) -> None:
        pass

    def sound_bytes(self, *a) -> bytes:
        return b""

    def ui_surface(self, *a, **k):
        return None

    def close(self) -> None:
        pass

    # ── 其余视觉/信息查询：一律返回保守空值，避免崩溃 ────────────────
    def __getattr__(self, name: str):
        if name.endswith("frames") or name.endswith("_origin"):
            return lambda *a, **k: []
        if name == "character_navel_px":
            return lambda *a, **k: (0, 0)
        if name.endswith("_info") or name.endswith("_price") \
                or name.startswith("damage_digits"):
            return lambda *a, **k: {}
        if name.endswith("_icon") or name.endswith("icon") \
                or name.endswith("surface"):
            return lambda *a, **k: self._tile
        return lambda *a, **k: None
