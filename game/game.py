"""游戏主场景：装配地图 / 生成 life 实体 / 主循环（60fps 固定步长）。

流程：加载资源 → 生成玩家 / 怪物 / NPC → 主循环（输入 → 更新 → 绘制）
出生 / 死亡重生：出生在入口 portal；HP 归零显示死亡界面，按 R 回到出生点并重置怪物。
"""

from __future__ import annotations

import os
from typing import List, Optional

import pygame

from . import settings
from .assets import Assets
from .physics import Physics
from .camera import Camera
from .audio import Audio
from .player import Player
from .monster import Monster
from .npc import NPC
from .combat import Combat
from .combat import DamageNumber
from .effects import Effect
from .ui import UI
from .panels import Panels

# 输入对象（把 pygame 按键抽象成 Player.update 需要的形状）
class _Keys:
    left = False
    right = False
    up = False
    down = False
    jump = False       # 按住跳
    attack = False
    drop = False       # 下跳


class Game:
    def __init__(self):
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        pygame.init()
        self.screen = pygame.display.set_mode(
            (settings.WINDOW_W, settings.WINDOW_H))
        pygame.display.set_caption(
            f"Maplestory 113 · {settings.MAP_ID} · pygame")
        self.canvas = pygame.Surface((settings.VIEW_W, settings.VIEW_H))
        self.clock = pygame.time.Clock()
        self.running = True

        # 资源
        self.assets = Assets(settings.MAP_ID, settings.REGION)
        self.physics = Physics(self.assets.footholds, self.assets.ropes)
        self.camera = Camera(self.assets.map_width, self.assets.map_height,
                             self.assets.bounds["left"], self.assets.bounds["top"])
        self.audio = Audio(self.assets, self.assets.map_bgm_path())
        self.combat = Combat(self.assets)
        self.ui = UI(self.assets)
        self.panels = Panels(self.ui, self.assets)

        # 出生点：入口 portal（sp，type 0）
        spawn = self._find_spawn()
        self.spawn_x = spawn[0]
        self.spawn_y = spawn[1]

        self.player = Player(self.assets, self.spawn_x, self.spawn_y)
        self.player.facing_right = True
        # 落地吸附到出生点的 foothold
        self._place_player_at_spawn()

        self.monsters: List[Monster] = []
        self.npcs: List[NPC] = []
        self.hits: List[dict] = []
        self._life_mobs = [d for d in self.assets.life if d["type"] == "mob"]
        self._life_npcs = [d for d in self.assets.life if d["type"] == "npc"]
        self._spawn_life()

        self.keys = _Keys()
        self.dead = False
        self.spawn_grace = settings.SPAWN_GRACE

        self.audio.play_bgm()
        self.ui.show_dialog("歡迎", ["冒險島 v113 · 弓箭手村東部小山",
                                     "A/D(或←→) 移動  空格 跳躍  S+空格 下跳",
                                     "W(或↑) 爬繩/梯  J 攻擊  1/2 技能  F 喝藥",
                                     "I 道具欄  K 技能欄  Enter 對話  R 復活",
                                     "（Enter/空格/Esc 關閉對話框）"])

    # ── 生成 ───────────────────────────────────────────────────────
    def _find_spawn(self):
        for p in self.assets.portals:
            if p["name"] == "sp" and p["type"] == 0:
                return float(p["x"]), float(p["y"])
        return 0.0, 0.0

    def _spawn_life(self) -> None:
        self.monsters = [Monster(self.assets, d, i, self.physics)
                         for i, d in enumerate(self._life_mobs)]
        self.npcs = [NPC(self.assets, d, i)
                     for i, d in enumerate(self._life_npcs)]

    # ── 输入 ───────────────────────────────────────────────────────
    def _handle_input(self) -> None:
        pressed = pygame.key.get_pressed()
        # WASD 与方向键并存
        self.keys.left = bool(pressed[pygame.K_LEFT] or pressed[pygame.K_a])
        self.keys.right = bool(pressed[pygame.K_RIGHT] or pressed[pygame.K_d])
        self.keys.up = bool(pressed[pygame.K_UP] or pressed[pygame.K_w])
        self.keys.down = bool(pressed[pygame.K_DOWN] or pressed[pygame.K_s])
        self.keys.attack = bool(pressed[pygame.K_j])
        self.keys.jump = bool(pressed[pygame.K_SPACE])

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # 对话框模态期间不响应面板点击
                if not self.ui.dialog_visible and not self.dead:
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    self.panels.handle_click((cx, cy), self.player)
            elif event.type == pygame.KEYDOWN:
                if self.dead:
                    if event.key == pygame.K_r:
                        self.respawn()
                    continue
                # 对话框打开时：Enter/空格/Esc 关闭（模态）
                if self.ui.dialog_visible:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                     pygame.K_SPACE, pygame.K_ESCAPE):
                        self.ui.hide_dialog()
                    continue
                if event.key == pygame.K_i:
                    self.panels.toggle_inventory()
                elif event.key == pygame.K_k:
                    self.panels.toggle_skill()
                elif event.key == pygame.K_f:
                    if self.player.use_potion():
                        self.audio.play("PickUpItem", 0.4)
                elif event.key in (pygame.K_1, pygame.K_2):
                    self._cast_skill(event.key - pygame.K_1 + 1)
                elif event.key == pygame.K_w:
                    # W 只用于上绳/梯（长按逻辑在 Player.update 中处理），不触发跳跃
                    pass
                elif event.key in (pygame.K_SPACE, pygame.K_UP):
                    if self.keys.down:
                        self.player.drop_through(self.physics)
                    elif self.player.climbing:
                        # 只有空格从绳上跳下；↑ 在绳上继续爬
                        if event.key == pygame.K_SPACE:
                            self.audio.play("Jump", 0.5)
                            self.player.jump()
                    elif (self.physics.rope_at(self.player.x, self.player.y) is None
                          or event.key == pygame.K_SPACE):
                        # 绳边按 ↑ 是爬绳意图，不起跳
                        if self.player.on_ground:
                            self.audio.play("Jump", 0.5)
                        self.player.jump()
                elif event.key == pygame.K_j:
                    self.player.start_attack()
                elif event.key in (pygame.K_DOWN, pygame.K_s) and self.keys.jump:
                    self.player.drop_through(self.physics)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._try_talk()

        # 兜底：弹窗瞬间按住的 J 等按键事件会被模态分支吞掉，
        # 用持续按键状态补触发攻击（按下即生效，无需等松开重按）
        if (self.keys.attack and not self.ui.dialog_visible
                and not self.dead and not self.player.attacking):
            self.player.start_attack()

    def _cast_skill(self, hotkey: int) -> None:
        """按快捷键施放技能（1/2）。成功则播放技能施放特效。"""
        sid = settings.HOTKEY_SKILLS.get(hotkey)
        if sid is None:
            return
        data = self.player.skills.cast(sid, self.player.level)
        if data is None:
            return
        if self.player.start_attack(data):
            eff = self.assets.skill_effect_frames(sid)
            if eff:
                self.combat.effects.append(Effect(
                    eff, self.player.x, self.player.y))

    def _try_talk(self) -> None:
        for npc in self.npcs:
            if npc.rect().colliderect(
                    pygame.Rect(int(self.player.x - 20), int(self.player.y - 40), 40, 80)):
                self.ui.show_dialog(npc.name, ["你好，冒險者！", "小心東邊山丘上的怪物。",
                                               "攻擊按 J，擊敗怪物可獲得經驗與掉落物。"])
                self.ui.dialog_visible = True
                return

    # ── 重生 ───────────────────────────────────────────────────────
    def _place_player_at_spawn(self) -> None:
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
        fh = self.physics.grounded_surface(p.x, p.feet_y)
        if fh is not None:
            p.y = fh.y_at(p.x) - settings.FEET_OFFSET
            p.on_ground = True

    def respawn(self) -> None:
        self.dead = False
        self.spawn_grace = settings.SPAWN_GRACE
        self.ui.hide_death()
        self.ui.hide_dialog()
        self.player.hp = self.player.max_hp
        self.player.attacking = False
        self.player.hurt_timer = 0.0
        self.player.invuln_timer = 0.0
        self._place_player_at_spawn()
        self._spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()

    # ── 更新 ───────────────────────────────────────────────────────
    def _update(self, dt: float) -> None:
        if self.dead:
            return

        # 模态对话框：暂停世界。既防止玩家在弹窗背后被咬/乱状态，
        # 也保证关闭对话框后攻击等输入恢复正常节奏
        if self.ui.dialog_visible:
            return

        # 出生保护计时
        if self.spawn_grace > 0:
            self.spawn_grace -= dt

        # 玩家
        self.player.update(dt, self.keys, self.physics, self.audio)

        # 掉出地图底部：回出生点并扣血（避免永远下坠）
        if self.player.y > self.assets.map_height + 80:
            self.player.damage(settings.FALL_OUT_DAMAGE)
            self.combat.numbers.append(DamageNumber(
                self.player.x, self.player.y - 40,
                settings.FALL_OUT_DAMAGE, (120, 180, 255)))
            self._place_player_at_spawn()

        # 攻击判定
        if self.player.attacking:
            self.combat.player_attack(self.player, self.monsters)

        # 经验结算（击杀累积后逐条发放，可升级；升级播官方特效不弹窗）
        while self.combat.pending_exp:
            amount = self.combat.pending_exp.pop(0)
            if self.player.gain_exp(amount):
                self.audio.play("LevelUp", 0.6)
                # 特效按角色锚点居中，整体抬高些更接近原版观感
                self.combat.effects.append(Effect(
                    self.assets.levelup_frames(), self.player.x, self.player.y - 45))

        # 怪物
        self.hits.clear()
        no_aggro = self.spawn_grace > 0
        for mob in self.monsters:
            mob.update(dt, self.player.x, self.player.y, self.hits, self.audio,
                       no_aggro=no_aggro)
        # 移除已消失的怪物
        self.monsters = [m for m in self.monsters
                         if not (m.dead and m.remove_after <= 0)]
        self.combat.apply_mob_hits(self.player, self.hits)

        # NPC
        for npc in self.npcs:
            npc.update(dt)

        # 拾取
        if self.combat.pickup(self.player):
            self.audio.play("PickUpItem", 0.5)

        # 死亡检测
        if self.player.hp <= 0:
            self.dead = True
            self.ui.show_death()
            self.audio.play("GameIn", 0.4)

        self.combat.update(dt, self.player)
        self.camera.center_on(self.player.x, self.player.y)

    # ── 绘制 ───────────────────────────────────────────────────────
    def _draw(self) -> None:
        # 地图
        self.canvas.blit(
            self.assets.map_surface, (0, 0),
            pygame.Rect(self.camera.img_x, self.camera.img_y,
                        settings.VIEW_W, settings.VIEW_H))
        # 掉落物（地图之上，实体之下）
        self.combat.draw(self.canvas, self.camera)
        # NPC / 怪物
        for npc in self.npcs:
            npc.draw(self.canvas, self.camera)
        for mob in self.monsters:
            mob.draw(self.canvas, self.camera)
        # 玩家
        if not self.dead:
            self.player.draw(self.canvas, self.camera)
        # 命中火花 / 升级特效（实体之上）
        self.combat.draw_effects(self.canvas, self.camera)
        # HUD / 面板 / 对话框 / 死亡
        self.ui.draw_hud(self.canvas, self.player, self.combat)
        self.panels.draw_quickslots(self.canvas, self.player)
        self.panels.draw(self.canvas, self.player, self.combat.meso)
        self.ui.draw_dialog(self.canvas)
        self.ui.draw_death(self.canvas)

        # 2x 放大到窗口
        scaled = pygame.transform.scale(
            self.canvas, (settings.WINDOW_W, settings.WINDOW_H))
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()

    # ── 主循环 ─────────────────────────────────────────────────────
    def run(self) -> None:
        while self.running:
            # 尖峰帧（切窗回来/卡顿）限步长：单帧重力下陷必须留在
            # grounded_surface 容差内（G*dt^2 < 2.5px），否则会误穿地
            dt = min(self.clock.tick(settings.FPS) / 1000.0, 0.035)
            self._handle_input()
            self._update(dt)
            self._draw()
        self._shutdown()

    def _shutdown(self) -> None:
        self.audio.close()
        self.assets.close()
        pygame.quit()
