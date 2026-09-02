"""World：地图场景 —— 子系统组装、实体生命周期、每帧更新/绘制。

从 Game 中抽出。World 持有：assets / physics / camera / combat / minimap /
player / monsters / npcs / spawn / 重生队列 / 传送门冷却。
UI 覆盖层（对话 / 横幅 / 淡入淡出 / 死亡界面）、存档、地图切换的「加载状态机」
仍留在 Game；World 通过返回值或回调把需要 Game 处理的事件（如切图、重定位）
交还上层。

坐标约定（与 settings 一致）：y 向下为正，navel 为角色锚点，脚底 = y + FEET_OFFSET。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game import settings
from game.core import travel
from game import features
from game.core.animation import Animation
from game.render.assets import Assets
from game.core.camera import Camera
from game.systems.combat import Combat, DamageNumber
from game.render.effects import Effect
from game.render.minimap import MiniMap
from game.entities.monster import Monster
from game.entities.npc import NPC
from game.core.physics import Physics
from game.entities.player import Player


def resolve_saved_spawn(physics: Physics, saved: Optional[Tuple[float, float]],
                        fallback: Tuple[float, float]) -> Tuple[float, float]:
    """存档坐标落地校验：saved 为 (x, 脚底 y)。坠落途中（穿地到线下很远）
    写下的坐标在本帧无穿线可接、会一进图就继续掉出地面；spawn_surface 在容差
    内找不到支撑面时判无效，回退出生门 fallback。"""
    if saved is None:
        return fallback
    x, feet = saved
    if physics.spawn_surface(x, feet) is not None:
        return saved
    return fallback


class World:
    """单张地图场景：装配物理/相机/战斗/小地图，并推进实体与绘制。

    构造即完成该图的世界构建（出生点查找 → 玩家 → 生命实体生成）。
    """

    def __init__(self, assets: Assets, quest_defs, save_data):
        self.assets = assets
        self.physics = Physics(assets.footholds, assets.ropes,
                               bounds=assets.bounds)
        self.camera = Camera(assets.map_width, assets.map_height,
                             assets.bounds["left"], assets.bounds["top"])
        self.combat = Combat(assets)
        self.minimap = MiniMap(
            assets.footholds, assets.ropes, assets.portals, assets.bounds,
            assets.map_width, assets.map_height,
            mag=(assets.map_desc.get("minimap") or {}).get("mag"),
            canvas=assets.minimap_surface(),
            map_surface=assets.map_surface)

        spawn = self._find_spawn()
        self.spawn_x, self.spawn_y = spawn[0], spawn[1]
        if save_data:
            pd = save_data["player"]
            saved = (float(pd["x"]), float(pd["y"]) + settings.FEET_OFFSET)
            self.spawn_x, self.spawn_y = resolve_saved_spawn(
                self.physics, saved, (self.spawn_x, self.spawn_y))

        self.player = Player(assets, self.spawn_x, self.spawn_y,
                             quest_defs=quest_defs, save_data=save_data)
        if not save_data:
            self.player.facing_right = True
        # 落地吸附到出生点的 foothold
        self.place_player_at_spawn()

        self.monsters: List[Monster] = []
        self.npcs: List[NPC] = []
        self.hits: List[dict] = []
        self._life_mobs = [d for d in assets.life if d["type"] == "mob"]
        self._life_npcs = [d for d in assets.life if d["type"] == "npc"]
        self._respawn_queue: List[Tuple[float, dict]] = []
        self._portal_cooldown = 0.0
        self._portal_pulse = 0.0
        self.spawn_life()

    # ── 出生 / 生成 ───────────────────────────────────────────────
    def _find_spawn(self) -> Tuple[float, float]:
        for p in self.assets.portals:
            if p["name"] == "sp" and p["type"] == 0:
                return float(p["x"]), float(p["y"])
        return 0.0, 0.0

    def spawn_life(self) -> None:
        self.monsters = [Monster(self.assets, d, i, self.physics)
                         for i, d in enumerate(self._life_mobs)]
        self._respawn_queue = []
        self.npcs = [NPC(self.assets, d, i)
                     for i, d in enumerate(self._life_npcs)]
        # 特性注入：如原版不可达的转职导师，在指定出生图额外生成一个实例
        for npc_id, nx, ny in features.TRAINER_SPAWNS.get(self.assets.map_id, ()):
            self.npcs.append(NPC(self.assets, {
                "id": npc_id, "x": nx, "cy": ny}, len(self.npcs)))

    def tick_respawns(self, dt: float) -> None:
        """重生队列计时：mobTime>0 按其毫秒数，否则用 MOB_RESPAWN_DELAY 兜底。"""
        if not self._respawn_queue:
            return
        still: List[Tuple[float, dict]] = []
        for remaining, data in self._respawn_queue:
            remaining -= dt
            if remaining <= 0:
                self.monsters.append(
                    Monster(self.assets, data, len(self.monsters), self.physics))
            else:
                still.append((remaining, data))
        self._respawn_queue = still

    def place_player_at_spawn(self) -> None:
        p = self.player
        p.x = self.spawn_x
        p.y = self.spawn_y - settings.FEET_OFFSET
        p.vx = p.vy = 0.0
        p.on_ground = False
        p.climbing = False
        p.attacking = False
        p.attack_timer = 0.0
        p.drop_layers.clear()
        p.drop_timer = 0.0
        fh = self.physics.spawn_surface(p.x, p.feet_y)
        if fh is not None:
            p.y = fh.y_at(p.x) - settings.FEET_OFFSET
            p.on_ground = True
            p.cur_fh = fh
            p.ground_layer = fh.layer

    def respawn_scene(self) -> None:
        """重生：实体回到出生点、重建生命、清空战斗残留（UI/淡入由 Game 处理）。"""
        self.place_player_at_spawn()
        self.spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()
        self.combat.arrows.clear()

    # ── 传送门 / 地图切换 ─────────────────────────────────────────
    def usable_portals(self) -> List[dict]:
        return travel.usable_portals(self.assets.portals,
                                     self.assets.map_renderer.has_map,
                                     self.assets.map_id)

    def portal_at_feet(self) -> Optional[dict]:
        """玩家脚底重叠、且此刻可触发的传送门。"""
        feet = self.player.y + settings.FEET_OFFSET
        pr = pygame.Rect(int(self.player.x - 12), int(feet - 12), 24, 24)
        for p in self.usable_portals():
            prt = pygame.Rect(int(p["x"]) - 14, int(p["y"]) - 14, 28, 28)
            if pr.colliderect(prt):
                return p
        return None

    def check_portal(self, dt: float, up_pressed: bool) -> Optional[dict]:
        """站在可通行传送门上触发切图；回传要切换的门，未触发回 None。

        按↑门需 up 键（up_pressed），碰撞门碰到即走。冷却在此递减。
        """
        if self._portal_cooldown > 0:
            self._portal_cooldown -= dt
            return None
        p = self.portal_at_feet()
        if p is None:
            return None
        if p["trigger"] == "up" and not up_pressed:
            return None
        return p

    def portal_position(self, portal_name: Optional[str]):
        """目标地图出生点：优先指定 portal，其次 sp 入口。"""
        for p in self.assets.portals:
            if portal_name and p.get("name") == portal_name:
                return float(p["x"]), float(p["y"])
        for p in self.assets.portals:
            if p.get("type") == 0:      # sp
                return float(p["x"]), float(p["y"])
        return float(self.assets.bounds["left"]), float(self.assets.bounds["top"])

    def enter_same_map(self, portal: dict) -> None:
        """同图瞬移门：不重载地图，直接落地到目标门位置（原版 psh 行为）。"""
        self._portal_cooldown = 0.8
        sx, sy = self.portal_position(portal.get("targetName"))
        self.spawn_x, self.spawn_y = sx, sy
        self.place_player_at_spawn()

    def finish_loading(self, portal_name: Optional[str]) -> None:
        """切图：后台渲染完成后，重建本图物理/相机/小地图、出生点与生命实体。"""
        self.physics = Physics(self.assets.footholds, self.assets.ropes,
                               bounds=self.assets.bounds)
        self.camera = Camera(self.assets.map_width, self.assets.map_height,
                             self.assets.bounds["left"], self.assets.bounds["top"])
        self._life_mobs = [d for d in self.assets.life if d["type"] == "mob"]
        self._life_npcs = [d for d in self.assets.life if d["type"] == "npc"]

        sx, sy = self.portal_position(portal_name)
        self.spawn_x, self.spawn_y = sx, sy
        self.minimap.set_map(
            self.assets.footholds, self.assets.ropes, self.assets.portals,
            self.assets.bounds, self.assets.map_width, self.assets.map_height,
            mag=(self.assets.map_desc.get("minimap") or {}).get("mag"),
            canvas=self.assets.minimap_surface(),
            map_surface=self.assets.map_surface)
        self.place_player_at_spawn()
        self.spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()
        self.combat.arrows.clear()
        self.hits.clear()
        self._portal_cooldown = 0.8
        self.preload_neighbors()

    def preload_neighbors(self) -> None:
        """把当前图所有可通行传送门的目标图后台预热进 LRU 缓存，秒开下张。"""
        targets = {p["target_id"] for p in self.usable_portals()}
        targets.discard(self.assets.map_id)
        if targets:
            self.assets.preload_neighbors(targets)

    # ── 每帧更新 ───────────────────────────────────────────────────
    def update(self, dt: float, keys, spawn_grace: float, *,
               audio=None, portal_blocked: bool = False) -> Optional[dict]:
        """推进世界一帧（玩家/怪物/箭/NPC/战斗/相机）。

        回传要切换的传送门（Game 据此启动地图加载），否则 None。
        """
        self._portal_pulse += dt

        # 玩家
        self.player.update(dt, keys, self.physics, audio)

        # 传送门检测（弹窗时屏蔽）
        if not portal_blocked:
            portal = self.check_portal(dt, bool(keys.up))
            if portal is not None:
                return portal

        # 掉出地图底部：回出生点并扣血（避免永远下坠）
        if self.player.y > self.assets.map_height + 80:
            self.player.damage(settings.FALL_OUT_DAMAGE)
            self.combat.numbers.append(DamageNumber(
                self.player.x, self.player.y - 40,
                settings.FALL_OUT_DAMAGE, "blue"))
            self.place_player_at_spawn()

        # 攻击判定：远程起手一次性生成箭（近战仍在首帧结算）
        if self.player.attacking:
            if self.player.is_ranged():
                if not self.player.attack_projectile_spawned:
                    self.player.attack_projectile_spawned = True
                    self.combat.spawn_arrows(self.player, self.player.pending_skill)
            else:
                self.combat.player_attack(self.player, self.monsters)

        # 经验结算（击杀累积后逐条发放，可升级；升级播官方特效不弹窗）
        while self.combat.pending_exp:
            amount = self.combat.pending_exp.pop(0)
            if self.player.gain_exp(amount):
                audio and audio.play("LevelUp", 0.6)
                self.combat.effects.append(Effect(
                    self.assets.levelup_frames(), self.player.x,
                    self.player.y - 45))

        # 怪物
        self.hits.clear()
        no_aggro = spawn_grace > 0
        for mob in self.monsters:
            mob.update(dt, self.player.x, self.player.y, self.hits, audio,
                       no_aggro=no_aggro)
        alive: List[Monster] = []
        for m in self.monsters:
            if m.dead and m.remove_after <= 0:
                delay = (m.mob_time / 1000.0 if m.mob_time > 0
                         else settings.MOB_RESPAWN_DELAY)
                self._respawn_queue.append((delay, m.life_data))
            else:
                alive.append(m)
        self.monsters = alive
        self.tick_respawns(dt)
        self.combat.apply_mob_hits(self.player, self.hits)

        # 飞行中的箭（在怪物移动之后结算）
        self.combat.update_arrows(dt, self.monsters, self.player)

        # NPC
        for npc in self.npcs:
            npc.update(dt)

        self.combat.update(dt)
        self.camera.center_on(self.player.x, self.player.y)
        return None

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, npc_marker, player_visible: bool) -> None:
        """画本图所有世界实体（地图/传送门/掉落/NPC/怪物/玩家/箭/特效）。"""
        self.assets_map_surface_blit(surface)
        self.draw_portals(surface)
        self.combat.draw(surface, self.camera)
        for npc in self.npcs:
            npc.draw(surface, self.camera, npc_marker(npc))
        for mob in self.monsters:
            mob.draw(surface, self.camera)
        if player_visible:
            self.player.draw(surface, self.camera)
        self.combat.draw_arrows(surface, self.camera)
        self.combat.draw_effects(surface, self.camera)

    def assets_map_surface_blit(self, surface: pygame.Surface) -> None:
        surface.blit(
            self.assets.map_surface, (0, 0),
            pygame.Rect(self.camera.img_x, self.camera.img_y,
                        settings.VIEW_W, settings.VIEW_H))

    def draw_portals(self, surface: pygame.Surface) -> None:
        frames = self.assets.portal_frames()
        shrink = self.assets.portal_shrink_frames()
        if not frames:
            return
        idx = Animation.frame_at(frames, self._portal_pulse * 1000.0)
        sidx = Animation.frame_at(shrink, self._portal_pulse * 1000.0)
        standing = self.portal_at_feet()
        for p in self.usable_portals():
            if p.get("trigger") != "up" or p.get("hidden"):
                continue
            sx, sy = self.camera.to_screen(p["x"], p["y"])
            surf, origin, _ = (shrink[sidx] if p.get("same_map") else frames[idx])
            rect = surf.get_rect()
            rect.centerx = int(sx)
            rect.bottom = int(sy) + 2
            surface.blit(surf, rect.topleft)
            if standing is not None and standing["name"] == p["name"]:
                pygame.draw.ellipse(surface, (255, 255, 140, 220),
                                    (rect.centerx - 18, rect.bottom - 10, 36, 14), 3)
