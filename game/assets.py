"""资源管线：把 113 WZ 资产预渲染成 pygame 可用的 Surface / 音效。

职责：
  · 打开全部需要的 WZ 档案（Map / Character / Mob / Npc / String / Sound）
  · 预渲染整张地图为一张大 Surface（相机按视口 blit 子区域）
  · 按 (equips, pose, flip) 缓存角色姿态帧；按 (mob, action, flip) 缓存怪物帧；
    按 (npc, action, flip) 缓存 NPC 帧 —— 均为 [(pygame.Surface, delay_ms)] + 锚点信息
  · 名字查询（地图 / 怪物 / NPC / 物品）与 BGM / 音效字节提取

坐标约定：pygame Surface 像素 = WZ 世界坐标平移 (bounds.left, bounds.top) 之后的坐标。
"""

from __future__ import annotations

import io
import os
import threading
import traceback
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pygame
from PIL import Image

from wzpy.wz_file import WzFile
from wzpy.map import MapRenderer
from wzpy.mob import MobRenderer
from wzpy.character import CharacterRenderer, DEFAULT_EAR_TYPE
from wzpy.properties import WzCanvasProperty, WzUolProperty

from . import settings
from .jobs import is_ranged_weapon, resolve_skill_img
from .localize import to_simplified

# 攻击姿态回退顺序（玩家攻击用）
ATTACK_POSES = ("swingO1", "swingO2", "swingO3", "stabO1", "stabO2")


class Assets:
    """持有所有 WZ 源与渲染缓存。线程安全（加载期在单线程完成）。"""

    def __init__(self, map_id: str = settings.MAP_ID, region: str = settings.REGION):
        self.map_id = map_id
        self.region = region
        self.wz = {
            "Map": WzFile.open(str(settings.WZ_DIR / "Map.wz"), region=region),
            "Character": WzFile.open(str(settings.WZ_DIR / "Character.wz"), region=region),
            "Mob": WzFile.open(str(settings.WZ_DIR / "Mob.wz"), region=region),
            "Npc": WzFile.open(str(settings.WZ_DIR / "Npc.wz"), region=region),
            "String": WzFile.open(str(settings.WZ_DIR / "String.wz"), region=region),
            "Sound": WzFile.open(str(settings.WZ_DIR / "Sound.wz"), region=region),
            "UI": WzFile.open(str(settings.WZ_DIR / "UI.wz"), region=region),
            "Effect": WzFile.open(str(settings.WZ_DIR / "Effect.wz"), region=region),
            "Skill": WzFile.open(str(settings.WZ_DIR / "Skill.wz"), region=region),
            "Quest": WzFile.open(str(settings.WZ_DIR / "Quest.wz"), region=region),
        }

        self.map_renderer = MapRenderer(
            self.wz["Map"], string_source=self.wz["String"],
            mob_source=self.wz["Mob"], npc_source=self.wz["Npc"],
            region=region,
        )
        self.mob_renderer = MobRenderer(
            self.wz["Mob"], string_source=self.wz["String"],
            item_source=self.wz["String"], character_source=self.wz["Character"],
            region=region,
        )
        self.char_renderer = CharacterRenderer(self.wz["Character"], region=region)

        self._char_cache: Dict[Tuple, Any] = {}
        self._mob_cache: Dict[Tuple, Any] = {}
        self._npc_cache: Dict[Tuple, Any] = {}
        self._sound_cache: Dict[str, bytes] = {}
        self._ui_cache: Dict[Tuple, Any] = {}
        self._effect_cache: Dict[Tuple, Any] = {}
        self._icon_cache: Dict[str, Any] = {}
        self._item_wz_obj = None   # Item.wz 较大，首次取图标时再打开

        # 后台线程加载地图
        self._load_thread: Optional[threading.Thread] = None
        self._load_result: Optional[Dict] = None

        # 地图静态数据
        self.load_map(map_id)

        # 后台预热各类常用素材，避免首次使用时主线程卡顿
        threading.Thread(target=self._warmup, daemon=True).start()

    def _warmup(self) -> None:
        """后台线程预热：预加载特效/传送门/UI/人物姿态等常用缓存。"""
        try:
            self.levelup_frames()
            self.portal_frames()
            self._item_wz()
            self.meso_frames()
            self.quest_icon_frames(0)
            self.quest_icon_frames(2)
            for sid in ("3001004", "3001005"):
                try:
                    self.skill_icon(sid)
                    self.skill_effect_frames(sid)
                    self.skill_hit_frames(sid)
                    self.skill_ball_frames(sid)
                except Exception:
                    pass
            self._warmup_ui()
            self._warmup_player_poses()
        except Exception:
            pass

    def _warmup_ui(self) -> None:
        """后台预热 HUD / 面板 / 对话框 的 UI 素材。"""
        paths: List[Tuple[str, str]] = [
            ("StatusBar.img", "base/backgrnd"),
            ("StatusBar.img", "gauge/bar"),
            ("StatusBar.img", "gauge/graduation"),
            ("StatusBar.img", "gauge/gray"),
            ("UIWindow.img", "Item/backgrnd"),
            ("UIWindow.img", "Equip/backgrnd"),
            ("UIWindow.img", "Skill/backgrnd"),
            ("UIWindow.img", "ShortCut/backgrnd"),
            ("UIWindow.img", "Quest/backgrnd2"),
            ("UIWindow.img", "Item/BtCoin/normal/0"),
            ("UIWindow.img", "Skill/BtSpUp/normal/0"),
            ("ChatBalloon.img", "arrow"),
            ("UtilDlgEx.img", "it"),
            ("UtilDlgEx.img", "ic"),
            ("UtilDlgEx.img", "is"),
        ]
        for d in "0123456789/":
            paths.append(("StatusBar.img", f"number/{d}"))
        for i in range(3):
            paths.append(("UIWindow.img", f"Item/Tab/enabled/{i}"))
            paths.append(("UIWindow.img", f"Item/Tab/disabled/{i}"))
            paths.append(("UIWindow.img", f"BtUIClose/normal/{i}"))
        for i in range(9):
            paths.append(("ChatBalloon.img", f"npc/{i}"))
        for img, path in paths:
            try:
                self.ui_surface(img, path)
            except Exception:
                pass

    def _warmup_player_poses(self) -> None:
        """后台预热玩家常驻姿态帧（站/走/跳/爬/攻，两种朝向）。"""
        equips = list(settings.DEFAULT_EQUIPS)
        for pose in ("stand1", "walk1", "jump", "ladder", "rope",
                     "swingO1", "swingO2"):
            try:
                self.character_frames(equips, pose, False)
                self.character_frames(equips, pose, True)
            except Exception:
                pass

    def load_map(self, map_id: str) -> None:
        """切换到另一张地图：重新读取描述 + 整图 Surface（WZ 句柄保持打开）。"""
        self.map_id = map_id
        self.map_desc = self.map_renderer.describe(map_id)
        self.bounds = self.map_desc["bounds"]
        self.footholds = self.map_desc["footholds"]
        self.ropes = self.map_desc["ropes"]
        self.portals = self.map_desc["portals"]
        self.life = self.map_desc["life"]
        self.map_surface = self._render_map_surface()
        self.map_width = self.bounds["width"]
        self.map_height = self.bounds["height"]

    # ── 异步加载 ─────────────────────────────────────────────────────
    def start_load_map(self, map_id: str) -> None:
        """在后台线程中渲染地图 PIL Image 并获取描述。"""
        self._load_thread = threading.Thread(
            target=self._load_map_worker, args=(map_id,), daemon=True)
        self._load_result = None
        self._load_thread.start()

    def _load_map_worker(self, map_id: str) -> None:
        """后台线程：渲染地图，完成后设 _load_result。"""
        try:
            desc = self.map_renderer.describe(map_id)
            img = self.map_renderer.compose(
                map_id, scale=1.0, time_ms=0,
                life=False, reactors=False, portals=False,
            )
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            bgm_path = ""
            try:
                root, _src = self.map_renderer._map_root(map_id)
                node = root.get("info/bgm")
                if node is not None:
                    bgm_path = str(getattr(node, "value", "") or "")
                else:
                    bgm_path = str(desc.get("bgm") or "")
            except Exception:
                bgm_path = str(desc.get("bgm") or "")
            self._load_result = {
                "map_id": map_id,
                "desc": desc,
                "img": img,
                "bgm_path": bgm_path,
            }
        except Exception as e:
            traceback.print_exc()
            self._load_result = {"error": e}

    @property
    def is_loading(self) -> bool:
        return self._load_thread is not None and self._load_thread.is_alive()

    @property
    def is_load_done(self) -> bool:
        return self._load_result is not None

    def finish_load_map(self) -> str:
        """完成后台加载，将结果应用到当前状态。必须在主线程调用。返回 bgm_path。"""
        result = self._load_result
        if result is None:
            return ""
        if "error" in result:
            self._load_thread = None
            self._load_result = None
            raise result["error"]
        self.map_id = result["map_id"]
        desc = result["desc"]
        self.map_desc = desc
        self.bounds = desc["bounds"]
        self.footholds = desc["footholds"]
        self.ropes = desc["ropes"]
        self.portals = desc["portals"]
        self.life = desc["life"]
        self.map_width = self.bounds["width"]
        self.map_height = self.bounds["height"]
        self.map_surface = pil_to_surface(result["img"])
        self._load_thread = None
        self._load_result = None
        return result["bgm_path"]

    # ── 地图 ────────────────────────────────────────────────────────
    def _render_map_surface(self) -> pygame.Surface:
        img = self.map_renderer.compose(
            self.map_id, scale=1.0, time_ms=0,
            life=False, reactors=False, portals=False,
        )
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        surf = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
        return surf.convert_alpha()

    def world_to_image(self, x: float, y: float) -> Tuple[float, float]:
        """世界坐标 → 地图 Surface 像素坐标。"""
        return (x - self.bounds["left"], y - self.bounds["top"])

    def image_to_world(self, px: float, py: float) -> Tuple[float, float]:
        return (px + self.bounds["left"], py + self.bounds["top"])

    # ── 角色 ────────────────────────────────────────────────────────
    def character_frames(
        self, equips: List[str], pose: str, flip: bool,
    ) -> List[Tuple[pygame.Surface, int]]:
        key = (tuple(equips), pose, flip)
        hit = self._char_cache.get(key)
        if hit is not None:
            return hit
        pil_frames = self.char_renderer.compose_animation(
            list(equips), pose, ear_type=DEFAULT_EAR_TYPE, flip=flip,
        )
        delays = self.char_renderer.pose_frame_delays(pose, "00002000")
        delays = delays or [100] * len(pil_frames)
        frames = [
            (pil_to_surface(f), delays[min(i, len(delays) - 1)])
            for i, f in enumerate(pil_frames)
        ]
        self._char_cache[key] = frames
        return frames

    def character_navel_px(self, equips: List[str], pose: str, flip: bool) -> Tuple[int, int]:
        """compose_animation 输出帧内 navel 的像素坐标（navel 世界 (0,0) 所在像素）。"""
        renderer = self.char_renderer
        hide_full, hide_set, cap_vslot = renderer._cap_hair_filter(list(equips))
        n_frames = len(renderer.pose_frame_delays(pose, "00002000")) or 3
        min_x = min_y = max_x = max_y = None
        for f in range(n_frames):
            pls, _ = renderer._build_placements(
                list(equips), pose, DEFAULT_EAR_TYPE,
                hide_full, hide_set, cap_vslot, f, return_anchors=True,
            )
            for p in pls:
                if p.top_left is None:
                    continue
                w = p.width_override if p.width_override is not None else p.pixel_canvas.width
                h = p.height_override if p.height_override is not None else p.pixel_canvas.height
                x0, y0 = p.top_left
                if min_x is None:
                    min_x, min_y, max_x, max_y = x0, y0, x0 + w, y0 + h
                else:
                    min_x = min(min_x, x0); min_y = min(min_y, y0)
                    max_x = max(max_x, x0 + w); max_y = max(max_y, y0 + h)
        if min_x is None:
            return (0, 0)
        npx = (0 - min_x, 0 - min_y)
        if flip:
            W = max(max_x - min_x, 1)
            npx = (W - 1 - npx[0], npx[1])
        return npx

    def attack_pose(self, equips: List[str]) -> str:
        weapon = next(
            (e for e in equips if self.char_renderer and _is_weapon(e)), None
        )
        poses = self.char_renderer.get_weapon_poses(weapon) if weapon else []
        if weapon is not None and is_ranged_weapon(weapon):
            # 弓用 shoot1、弩用 shoot2（原版拉弓动作），武器无该动作时回退近战表
            pref = "shoot1" if int(weapon) // 10000 == 145 else "shoot2"
            if pref in poses:
                return pref
        for pref in ATTACK_POSES:
            if pref in poses:
                return pref
        return ATTACK_POSES[0]

    # ── 怪物 ────────────────────────────────────────────────────────
    def mob_frames(
        self, mob_id: str, action: str, flip: bool = False,
    ) -> List[Tuple[pygame.Surface, int]]:
        key = (mob_id, action, flip)
        hit = self._mob_cache.get(key)
        if hit is not None:
            return hit
        frames = self._extract_action_frames(
            self.mob_renderer, self.wz["Mob"], mob_id, action, flip,
        )
        self._mob_cache[key] = frames
        return frames

    def mob_default_action(self, mob_id: str) -> str:
        try:
            d = self.mob_renderer.describe(mob_id)
        except Exception:
            return "move"
        return d.get("defaultAction") or "move"

    def mob_info(self, mob_id: str) -> Dict[str, Any]:
        try:
            return self.mob_renderer.describe(mob_id)
        except Exception:
            return {"name": mob_id, "stats": {}, "drops": []}

    def mob_origin(self, mob_id: str, action: str) -> Optional[Tuple[int, int]]:
        """读取该 action 第 0 帧的 origin；用于怪物世界坐标 → 像素定位。"""
        frames = self._mob_action_canvases(mob_id, action)
        if not frames:
            return None
        return _canvas_origin(frames[0])

    # ── NPC ─────────────────────────────────────────────────────────
    def npc_frames(
        self, npc_id: str, action: str = "stand", flip: bool = False,
    ) -> List[Tuple[pygame.Surface, int]]:
        key = (npc_id, action, flip)
        hit = self._npc_cache.get(key)
        if hit is not None:
            return hit
        frames = self._extract_npc_frames(npc_id, action, flip)
        self._npc_cache[key] = frames
        return frames

    def npc_origin(self, npc_id: str, action: str = "stand") -> Optional[Tuple[int, int]]:
        canvases = self._npc_action_canvases(npc_id, action)
        return _canvas_origin(canvases[0]) if canvases else None

    def npc_name(self, npc_id: str) -> str:
        try:
            image = self.wz["String"].root.get("Npc.img")
            node = image.parse().get(str(int(npc_id))) if image else None
            name = node.get("name").value if node and node.get("name") else f"NPC {npc_id}"
            return to_simplified(str(name))
        except Exception:
            return f"NPC {npc_id}"
    def _mob_action_canvases(self, mob_id: str, action: str) -> List[WzCanvasProperty]:
        try:
            root, _src = self.mob_renderer._mob_root(mob_id)
        except Exception:
            return []
        return self.mob_renderer._frames(root.get(action)) if root.get(action) else []

    def _npc_action_canvases(self, npc_id: str, action: str) -> List[WzCanvasProperty]:
        image = self.wz["Npc"].root.get(f"{str(int(npc_id)).zfill(7)}.img")
        if image is None:
            return []
        root = image.parse()
        # 跟随 link：info/link 指向真实 NPC（如 1012110 → 9010005）
        link = root.get("info/link")
        if link is not None:
            target = str(link.value).strip()
            try:
                target_id = str(int(target))
            except (TypeError, ValueError):
                target_id = ""
            if target_id and target_id != str(int(npc_id)):
                timg = self.wz["Npc"].root.get(f"{target_id.zfill(7)}.img")
                if timg is not None:
                    troot = timg.parse()
                    node = troot.get(action)
                    return _npc_canvases(node)
        node = root.get(action)
        return _npc_canvases(node)

    def _extract_npc_frames(
        self, npc_id: str, action: str, flip: bool,
    ) -> List[Tuple[pygame.Surface, int]]:
        canvases = self._npc_action_canvases(npc_id, action)
        frames = []
        for cv in canvases:
            img = _decode_canvas_prop(cv, self.region, self.wz["Npc"])
            if img is None:
                continue
            if flip:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            delay = _canvas_delay(cv)
            frames.append((pil_to_surface(img), delay))
        return frames

    def _extract_action_frames(
        self, renderer: MobRenderer, source: Any, mob_id: str, action: str, flip: bool,
    ) -> List[Tuple[pygame.Surface, int]]:
        canvases = self._mob_action_canvases(mob_id, action)
        frames = []
        for cv in canvases:
            img = _decode_canvas_prop(cv, self.region, source)
            if img is None:
                continue
            if flip:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            delay = _canvas_delay(cv)
            frames.append((pil_to_surface(img), delay))
        return frames

    # ── 音效 / BGM ──────────────────────────────────────────────────
    def sound_bytes(self, path: str) -> Optional[bytes]:
        """按 'Bgm03/Elfwood' 风格路径读取 Sound.wz 内嵌音频字节。"""
        if path in self._sound_cache:
            return self._sound_cache[path]
        parts = path.split("/")
        if not parts:
            return None
        img_name = parts[0]
        image = self.wz["Sound"].root.get(img_name if img_name.endswith(".img") else img_name + ".img")
        if image is None:
            return None
        node = image.parse()
        for seg in parts[1:]:
            nxt = node.get(seg) if hasattr(node, "get") else None
            if nxt is None:
                return None
            node = nxt
        if not hasattr(node, "_data_offset") or node._data_offset is None:
            return None
        sound_file = self.wz["Sound"]
        with sound_file.reader_lock:
            reader = sound_file.reader
            keep = reader.position
            reader.seek(node._data_offset)
            data = reader.read(node._data_length)
            reader.seek(keep)
        self._sound_cache[path] = data
        return data

    def map_bgm_path(self) -> str:
        try:
            root, _src = self.map_renderer._map_root(self.map_id)
            node = root.get("info/bgm")
            if node is not None:
                return str(getattr(node, "value", "") or "")
        except Exception:
            pass
        return str(self.map_desc.get("bgm") or "")

    # ── 名字 ────────────────────────────────────────────────────────
    def map_name(self) -> str:
        return to_simplified(self.map_desc.get("name") or f"Map {self.map_id}")

    def minimap_surface(self) -> Optional[pygame.Surface]:
        """官方小地图 canvas（整图缩略图），无则返回 None。缓存。"""
        key = f"minimap:{self.map_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        try:
            root, _src = self.map_renderer._map_root(self.map_id)
            mm = root.get("miniMap")
            cv = mm.get("canvas") if mm is not None else None
            if isinstance(cv, WzCanvasProperty):
                pil = _decode_canvas_prop(cv, self.region, self.wz["Map"])
                if pil is not None:
                    result = pil_to_surface(pil)
        except Exception:
            result = None
        self._icon_cache[key] = result
        return result

    def map_name_of(self, map_id) -> str:
        """任意地图 id → 名称（String.wz Map.img）。"""
        try:
            image = self.wz["String"].root.get("Map.img")
            if image is not None:
                for category in image.parse().children():
                    entry = category.get(str(int(map_id)))
                    if entry is not None and entry.get("mapName") is not None:
                        return to_simplified(str(entry.get("mapName").value))
        except Exception:
            pass
        try:
            root, _ = self.map_renderer._map_root(map_id)
            node = root.get("info/mapName")
            if node is not None:
                return to_simplified(str(getattr(node, "value", "") or ""))
        except Exception:
            pass
        return f"地图 {map_id}"

    def mob_name_of(self, mob_id) -> str:
        """任意怪物 id → 名称。"""
        try:
            d = self.mob_renderer.describe(mob_id)
            return to_simplified(d.get("name") or f"怪物 {mob_id}")
        except Exception:
            return f"怪物 {mob_id}"

    # ── UI.wz ───────────────────────────────────────────────────────
    def ui_surface(self, img: str, path: str):
        """从 UI.wz 取一张 canvas → (pygame.Surface, origin(x,y))。缓存。"""
        key = (img, path)
        hit = self._ui_cache.get(key)
        if hit is not None:
            return hit
        image = self.wz["UI"].root.images.get(img if img.endswith(".img") else img + ".img")
        result = None
        if image is not None:
            node = image.parse().get(path)
            if isinstance(node, WzCanvasProperty):
                pil = _decode_canvas_prop(node, self.region, self.wz["UI"])
                if pil is not None:
                    result = (pil_to_surface(pil), _canvas_origin(node))
        self._ui_cache[key] = result
        return result

    # ── Effect.wz / Skill.wz 帧动画 / Item.wz 图标 ─────────────────
    def effect_frames(self, wz_key: str, img_name: str, node_path: str) -> List:
        """取一个节点下的 canvas 子帧序列 → [(Surface, origin, delay_ms)]。缓存。"""
        key = (wz_key, img_name, node_path)
        hit = self._effect_cache.get(key)
        if hit is not None:
            return hit
        result: List[Tuple[pygame.Surface, Tuple[int, int], int]] = []
        image = self.wz[wz_key].root.images.get(img_name)
        if image is not None:
            node = image.parse().get(node_path)
            if node is not None:
                for child in node.children():
                    real = _resolve_uol(child)
                    if isinstance(real, WzCanvasProperty):
                        pil = _decode_canvas_prop(real, self.region, self.wz[wz_key])
                        if pil is not None:
                            result.append((pil_to_surface(pil),
                                           _canvas_origin(real), _canvas_delay(real)))
        self._effect_cache[key] = result
        return result

    def levelup_frames(self) -> List:
        """升级特效 Effect.wz/BasicEff.img/LevelUp。"""
        return self.effect_frames("Effect", "BasicEff.img", "LevelUp")

    def quest_icon_frames(self, index: int) -> List[Tuple[pygame.Surface, int]]:
        """NPC 头顶任务指示灯（UIWindow/QuestIcon/<i> 动画帧）。"""
        key = f"qicon:{index}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        frames: List[Tuple[pygame.Surface, int]] = []
        node = None
        try:
            root = self.wz["UI"].root.images.get("UIWindow.img")
            if root is not None:
                node = root.parse().get(f"QuestIcon/{index}")
        except Exception:
            node = None
        if node is not None:
            for child in node.children():
                real = _resolve_uol(child)
                if isinstance(real, WzCanvasProperty):
                    pil = _decode_canvas_prop(real, self.region, self.wz["UI"])
                    if pil is not None:
                        frames.append((pil_to_surface(pil), _canvas_delay(real)))
        self._icon_cache[key] = frames
        return frames

    def _item_wz(self):
        if self._item_wz_obj is None:
            from wzpy.wz_file import WzFile
            self._item_wz_obj = WzFile.open(
                str(settings.WZ_DIR / "Item.wz"), region=self.region)
        return self._item_wz_obj

    def item_icon(self, item_id: str) -> Optional[pygame.Surface]:
        """物品图标（Item.wz info/icon）；装备等不在本 WZ 子集返回 None。缓存。"""
        key = f"icon:{item_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        try:
            iid = int(item_id)
        except (TypeError, ValueError):
            iid = -1
        cat = iid // 10000
        sub = ("Consume" if 200 <= cat < 300
               else "Etc" if 400 <= cat < 500
               else "Install" if 500 <= cat < 600
               else "Special" if cat == 900 else None)
        if sub is not None:
            group = self._item_wz().root.subdirs.get(sub)
            img_name = f"{cat:04d}.img"
            if group is not None and img_name in group.images:
                node = group.images[img_name].parse().get(f"{iid:08d}/info/icon")
                if isinstance(node, WzCanvasProperty):
                    pil = _decode_canvas_prop(node, self.region, self._item_wz())
                    if pil is not None:
                        result = pil_to_surface(pil)
        self._icon_cache[key] = result
        return result

    # ── 传送门特效（Map.wz MapHelper.img portal/game/pv）────────────
    def portal_frames(self) -> List[Tuple[pygame.Surface, Tuple[int, int], int]]:
        """Map.wz/MapHelper.img/portal/game/pv 的 8 帧动画序列。"""
        key = "portal:pv"
        hit = self._effect_cache.get(key)
        if hit is not None:
            return hit
        result: List[Tuple[pygame.Surface, Tuple[int, int], int]] = []
        image = self.wz["Map"].root.images.get("MapHelper.img")
        if image is not None:
            node = image.parse().get("portal/game/pv")
            if node is not None:
                for child in node.children():
                    real = _resolve_uol(child)
                    if isinstance(real, WzCanvasProperty):
                        pil = _decode_canvas_prop(real, self.region, self.wz["Map"])
                        if pil is not None:
                            result.append((pil_to_surface(pil),
                                           _canvas_origin(real), _canvas_delay(real)))
        if not result:
            result = [(pygame.Surface((1, 1), pygame.SRCALPHA), (0, 0), 100)]
        self._effect_cache[key] = result
        return result

    def equip_subdir(self, item_id: str) -> Optional[str]:
        """装备 id → Character.wz 子目录名（按 id 前缀分类）。"""
        try:
            cat = int(item_id) // 10000
        except (TypeError, ValueError):
            return None
        table = {
            100: "Cap", 101: "Accessory", 102: "Accessory", 103: "Accessory",
            104: "Coat", 105: "Longcoat", 106: "Pants", 107: "Shoes",
            108: "Glove", 109: "Shield", 110: "Cape", 111: "Ring",
            112: "Pendant", 113: "Belt", 114: "Medal", 115: "Shoulder",
            116: "Pocket", 118: "Badge", 119: "Emblem",
            180: "PetEquip",
            190: "TamingMob", 191: "TamingMob", 193: "TamingMob",
            194: "TamingMob", 195: "TamingMob", 197: "TamingMob", 198: "TamingMob",
        }
        if cat in table:
            return table[cat]
        if 130 <= cat <= 149:
            return "Weapon"
        return None

    def equip_info(self, item_id: str) -> Optional[Dict[str, Any]]:
        """装备属性（Character.wz info）：islot / reqLevel / incPAD 等。缓存。"""
        key = f"eqinfo:{item_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        subdir = self.equip_subdir(item_id)
        if subdir is not None:
            grp = self.wz["Character"].root.subdirs.get(subdir)
            img_name = f"{int(item_id):08d}.img"
            if grp is not None and img_name in grp.images:
                info = grp.images[img_name].parse().get("info")
                if info is not None:
                    result = {c.name: getattr(c, "value", None)
                              for c in info.children()}
        self._icon_cache[key] = result
        return result

    def equip_icon(self, item_id: str) -> Optional[pygame.Surface]:
        """装备图标（Character.wz info/icon）。缓存。"""
        key = f"eqicon:{item_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        subdir = self.equip_subdir(item_id)
        if subdir is not None:
            grp = self.wz["Character"].root.subdirs.get(subdir)
            img_name = f"{int(item_id):08d}.img"
            if grp is not None and img_name in grp.images:
                node = grp.images[img_name].parse().get("info/icon")
                if isinstance(node, WzCanvasProperty):
                    pil = _decode_canvas_prop(node, self.region,
                                              self.wz["Character"])
                    if pil is not None:
                        result = pil_to_surface(pil)
        self._icon_cache[key] = result
        return result

    def consume_info(self, item_id: str) -> Optional[Dict[str, Any]]:
        """消耗品（Item.wz Consume）：info(price/slotMax) + spec(hp/mp 恢复)。缓存。"""
        key = f"consume:{item_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        try:
            iid = int(item_id)
        except (TypeError, ValueError):
            iid = -1
        if 2000000 <= iid < 3000000:
            group = self._item_wz().root.subdirs.get("Consume")
            img_name = f"{iid // 10000:04d}.img"
            if group is not None and img_name in group.images:
                root = group.images[img_name].parse()
                node = root.get(f"{iid:08d}")
                if node is not None:
                    result = {"spec": {}, "info": {}}
                    for part in ("info", "spec"):
                        sub = node.get(part)
                        if sub is not None:
                            result[part] = {c.name: getattr(c, "value", None)
                                            for c in sub.children()}
        self._icon_cache[key] = result
        return result

    def item_name(self, item_id: str) -> Optional[str]:
        """String.wz 物品名（消耗品 / 装备 / 其他）。缓存。"""
        key = f"name:{item_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        try:
            iid = int(item_id)
        except (TypeError, ValueError):
            iid = -1
        try:
            sz = self.wz["String"]
            if 1000000 <= iid < 2000000:
                subdir = self.equip_subdir(item_id)
                cat_map = {"Cap": "Cap", "Accessory": "Accessory",
                           "Coat": "Coat", "Longcoat": "Longcoat",
                           "Pants": "Pants", "Shoes": "Shoes",
                           "Glove": "Glove", "Shield": "Shield",
                           "Cape": "Cape", "Ring": "Ring",
                           "Pendant": "Pendant", "Belt": "Belt",
                           "Medal": "Medal", "Shoulder": "Shoulder",
                           "Pocket": "Pocket", "Badge": "Badge",
                           "Emblem": "Emblem", "Weapon": "Weapon",
                           "PetEquip": "PetEquip", "TamingMob": "Taming"}
                node = sz.root.images.get("Eqp.img")
                if node is not None and subdir in cat_map:
                    n = (node.parse().get(f"Eqp/{cat_map[subdir]}/{iid}"))
                    if n is not None:
                        nm = n.get("name")
                        result = str(nm.value) if nm is not None else None
            elif 2000000 <= iid < 3000000:
                node = sz.root.images.get("Consume.img")
                if node is not None:
                    n = node.parse().get(str(iid))
                    if n is not None:
                        nm = n.get("name")
                        result = str(nm.value) if nm is not None else None
            elif 4000000 <= iid < 5000000:
                node = sz.root.images.get("Etc.img")
                if node is not None:
                    root = node.parse()
                    n = root.get(str(iid))
                    if n is None:
                        n = root.get(f"Etc/{iid}")   # 部分 WZ 有 Etc 包裹层
                    if n is not None:
                        nm = n.get("name")
                        result = str(nm.value) if nm is not None else None
        except Exception:
            result = None
        result = to_simplified(result) if result else result
        self._icon_cache[key] = result
        return result

    def skill_icon(self, skill_id: str) -> Optional[pygame.Surface]:
        """技能图标（Skill.wz skill/<id>/icon）。缓存。"""
        key = f"skicon:{skill_id}"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        result = None
        img = self.wz["Skill"].root.images.get(resolve_skill_img(skill_id))
        if img is not None:
            node = img.parse().get(f"skill/{skill_id}/icon")
            if isinstance(node, WzCanvasProperty):
                pil = _decode_canvas_prop(node, self.region, self.wz["Skill"])
                if pil is not None:
                    result = pil_to_surface(pil)
        self._icon_cache[key] = result
        return result

    def skill_effect_frames(self, skill_id: str) -> List:
        """技能施放特效（角色身位播放）。"""
        return self.effect_frames("Skill", resolve_skill_img(skill_id),
                                  f"skill/{skill_id}/effect")

    def skill_hit_frames(self, skill_id: str = "1001004") -> List:
        """技能命中特效（怪物身位播放）。"""
        return self.effect_frames("Skill", resolve_skill_img(skill_id),
                                  f"skill/{skill_id}/hit/0")

    def skill_ball_frames(self, skill_id: str) -> List:
        """技能弹道贴图（如箭矢 ball/*），[(Surface, origin, delay_ms)]。"""
        return self.effect_frames("Skill", resolve_skill_img(skill_id),
                                  f"skill/{skill_id}/ball")

    def normal_arrow_frames(self) -> List:
        """普攻箭矢贴图：原版用箭矢物品（金币箭 2060000）的 bullet 节点渲染。"""
        key = ("Item", "0206.img", f"{settings.NORMAL_ARROW_ITEM_ID}/bullet")
        hit = self._effect_cache.get(key)
        if hit is not None:
            return hit
        result: List[Tuple[pygame.Surface, Tuple[int, int], int]] = []
        group = self._item_wz().root.subdirs.get("Consume")
        if group is not None and "0206.img" in group.images:
            node = group.images["0206.img"].parse().get(key[2])
            if node is not None:
                for child in node.children():
                    real = _resolve_uol(child)
                    if isinstance(real, WzCanvasProperty):
                        pil = _decode_canvas_prop(real, self.region, self._item_wz())
                        if pil is not None:
                            result.append((pil_to_surface(pil),
                                           _canvas_origin(real), _canvas_delay(real)))
        self._effect_cache[key] = result
        return result

    def meso_frames(self) -> List[Tuple[pygame.Surface, int]]:
        """金币（Item.wz/Special/09000000 iconRaw 的 4 帧旋转动画）。缓存。"""
        key = "meso"
        hit = self._icon_cache.get(key)
        if hit is not None:
            return hit
        frames: List[Tuple[pygame.Surface, int]] = []
        group = self._item_wz().root.subdirs.get("Special")
        if group is not None and "0900.img" in group.images:
            node = group.images["0900.img"].parse().get("09000000/iconRaw")
            if node is not None:
                for child in node.children():
                    real = _resolve_uol(child)
                    if isinstance(real, WzCanvasProperty):
                        pil = _decode_canvas_prop(real, self.region, self._item_wz())
                        if pil is not None:
                            frames.append((pil_to_surface(pil), _canvas_delay(real)))
        if not frames:
            frames = [(pygame.Surface((10, 10), pygame.SRCALPHA), 100)]
        self._icon_cache[key] = frames
        return frames

    def close(self) -> None:
        for wz in self.wz.values():
            try:
                wz.close()
            except Exception:
                pass
        if self._item_wz_obj is not None:
            try:
                self._item_wz_obj.close()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════

def pil_to_surface(img: Image.Image) -> pygame.Surface:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    surf = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
    return surf.convert_alpha()


def _is_weapon(eid: str) -> bool:
    try:
        return 130 <= int(eid) // 10000 <= 149
    except Exception:
        return False


def _resolve_uol(prop) -> Any:
    seen = set()
    while isinstance(prop, WzUolProperty) and prop.parent is not None:
        if id(prop) in seen:
            return None
        seen.add(id(prop))
        prop = prop.parent.get(str(prop.value))
    return prop


def _canvas_origin(cv: WzCanvasProperty) -> Tuple[int, int]:
    origin = _resolve_uol(cv.get("origin")) if hasattr(cv, "get") else None
    if origin is None:
        return (0, 0)
    try:
        return int(origin.x), int(origin.y)
    except Exception:
        return (0, 0)


def _canvas_delay(cv: WzCanvasProperty) -> int:
    delay = _resolve_uol(cv.get("delay")) if hasattr(cv, "get") else None
    try:
        return max(1, int(delay.value)) if delay is not None else 100
    except Exception:
        return 100


def _npc_canvases(node) -> List[WzCanvasProperty]:
    from wzpy.properties import WzSubProperty
    if node is None:
        return []
    node = _resolve_uol(node)
    if isinstance(node, WzCanvasProperty):
        return [node]
    if not isinstance(node, WzSubProperty):
        return []
    frames = []
    for child in node.children():
        if child.name.isdigit():
            real = _resolve_uol(child)
            if isinstance(real, WzCanvasProperty):
                frames.append(real)
            elif isinstance(real, WzSubProperty):
                frames.extend(_npc_canvases(real))
    return frames


def _decode_canvas_prop(cv: WzCanvasProperty, region: str, source: Any) -> Optional[Image.Image]:
    """解码单个 canvas 属性。带与 MapRenderer/MobRenderer 一致的容错。"""
    from wzpy.canvas import decode_canvas
    from wzpy.wz_package import resolve_canvas_link
    try:
        pixel = cv
        if not cv.has_pixels():
            linked = resolve_canvas_link(cv, source.root)
            if linked is None:
                return None
            pixel = linked
        return decode_canvas(pixel, region=region).convert("RGBA")
    except Exception:
        return None
