"""怪物实体：从地图 life 数据生成，AI 状态机 巡逻 → 追击 → 接触攻击 → 受击 → 死亡。

坐标：(x, y) 为怪物脚底锚点（WZ life.cy 为地面 y），sprite 用 origin 偏移定位。
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import pygame

from . import settings
from .assets import Assets


class Monster:
    def __init__(self, assets: Assets, data: dict, index: int,
                 physics=None):
        self.assets = assets
        self.mob_id = str(int(data["id"]))
        self.index = index
        self.x = float(data["x"])
        self.cy = float(data.get("cy") or data["y"])   # 地面接触 y
        self.rx0 = float(data.get("rx0") or data["x"])
        self.rx1 = float(data.get("rx1") or data["x"])
        self.flip = bool(data.get("flip"))

        # 脚下 foothold：巡逻/追击范围钳制到平台内，坡道上跟随高度，
        # 防止按地图 life 的 rx 范围走出平台边缘后悬空
        self.fh = physics.surface_under(self.x, self.cy) if physics else None
        if self.fh is not None:
            self.rx0 = max(self.rx0, self.fh.xmin + 6.0)
            self.rx1 = min(self.rx1, self.fh.xmax - 6.0)
            if self.rx0 > self.rx1:
                mid = (self.rx0 + self.rx1) / 2
                self.rx0 = self.rx1 = mid

        info = assets.mob_info(self.mob_id)
        stats = info.get("stats") or {}
        self.name = info.get("name") or f"Mob {self.mob_id}"
        self.max_hp = int(stats.get("maxHP") or 10)
        self.hp = self.max_hp
        self.exp = int(stats.get("exp") or 0)
        self.attack_power = int(stats.get("weaponAttack") or 10)
        self.speed = float(stats.get("speed") or 0)
        self.drops = info.get("drops") or []

        # 动作缓存
        self.action = "stand"
        self.frames: List[Tuple[pygame.Surface, int]] = []
        self.frame = 0
        self.accum = 0.0
        self.origin = (0, 0)
        self.dir = -1 if self.flip else 1   # 朝向：+1 右

        # AI 状态
        self.state = "patrol"     # patrol / chase / hit / die
        self.state_timer = 0.0
        self.hit_flash = 0.0
        self.attack_cooldown = 0.0
        self.dead = False
        self.remove_after = 0.0

        self._load_action("move" if self._has("move") else "stand")

    def _has(self, action: str) -> bool:
        try:
            return len(self.assets.mob_frames(self.mob_id, action)) > 0
        except Exception:
            return False

    def _load_action(self, action: str) -> None:
        if action == self.action and self.frames:
            return
        self.action = action
        self.frames = self.assets.mob_frames(self.mob_id, action)
        self.origin = self.assets.mob_origin(self.mob_id, action) or (0, 0)
        self.frame = 0
        self.accum = 0.0

    # ── 受击 / 死亡 ────────────────────────────────────────────────
    def take_hit(self, damage: int, from_x: Optional[float] = None) -> bool:
        if self.dead:
            return False
        self.hp -= damage
        self.state = "hit"
        self.state_timer = 0.25
        self.hit_flash = 0.15
        if from_x is not None and self.state_timer > 0:
            # 原版受击小击退（钳在巡逻平台内）
            away = 1 if self.x < from_x else -1
            self.x = min(max(self.x + away * 10.0, self.rx0), self.rx1)
            self._follow_ground()
        if self.hp <= 0:
            self.die()
            return True
        if self._has("hit1"):
            self._load_action("hit1")
        return False

    def die(self) -> None:
        self.dead = True
        self.state = "die"
        self.remove_after = 0.5
        action = "die1" if self._has("die1") else ("die" if self._has("die") else "hit1")
        self._load_action(action)

    # ── 每帧更新 ───────────────────────────────────────────────────
    def update(self, dt: float, player_x: float, player_y: float,
               mobs, audio=None, no_aggro: bool = False) -> None:
        if self.dead:
            self.remove_after -= dt
            self._tick_frame(dt)
            return

        if self.hit_flash > 0:
            self.hit_flash -= dt

        # 攻击冷却
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        dx = player_x - self.x
        dist = abs(dx)
        # 垂直距离：玩家脚底 vs 怪物地面 y（不同层平台不参与仇恨/接触伤害）
        player_feet = player_y + settings.FEET_OFFSET
        dy = abs(player_feet - self.cy)

        # 状态机
        if self.state == "hit":
            self.state_timer -= dt
            self._tick_frame(dt)
            if self.state_timer <= 0:
                self.state = "patrol"
            return

        # 追击逻辑（出生保护期内不追击；且只在同一层追击）
        chasing = ((not no_aggro) and dist <= settings.MOB_AGGRO_RANGE
                   and dy <= settings.MOB_AGGRO_Y_RANGE)
        speed = settings.MOB_CHASE_SPEED if chasing else settings.MOB_PATROL_SPEED

        if chasing and dist > settings.MOB_ATTACK_RANGE:
            self.state = "chase"
            step = speed * dt
            if dx > 0:
                self.x = min(self.x + step, player_x - 1)
                self.dir = 1
            else:
                self.x = max(self.x - step, player_x + 1)
                self.dir = -1
            # 不追出自己的巡逻平台（否则会悬空在平台外）
            self.x = min(max(self.x, self.rx0), self.rx1)
            self._follow_ground()
            self._load_action("move" if self._has("move") else "stand")
        elif chasing and dist <= settings.MOB_ATTACK_RANGE:
            self.state = "attack"
            self._load_action("stand")
        else:
            self.state = "patrol"
            # 在 rx0..rx1 之间巡逻
            self.x += self.dir * speed * dt
            if self.x <= self.rx0:
                self.x = self.rx0
                self.dir = 1
            elif self.x >= self.rx1:
                self.x = self.rx1
                self.dir = -1
            self._follow_ground()
            self._load_action("move" if self._has("move") else "stand")

        self._tick_frame(dt)

        # 接触伤害（近身且冷却完毕；出生保护期内不攻击；不同层不攻击）
        if ((not no_aggro) and dist <= settings.MOB_ATTACK_RANGE
                and dy <= settings.MOB_CONTACT_Y_RANGE
                and self.attack_cooldown <= 0):
            if audio:
                audio.play("GameIn", 0.3)
            mobs.append({
                "type": "contact",
                "amount": settings.MOB_CONTACT_DAMAGE,
                "x": self.x, "y": self.cy - 30,
                "id": self.mob_id,
            })
            self.attack_cooldown = 0.8

    def _follow_ground(self) -> None:
        """沿脚下 foothold 的高度走（坡道跟随，平台内不会悬空）。"""
        if self.fh is not None:
            self.cy = self.fh.y_at(self.x)

    def _tick_frame(self, dt: float) -> None:
        if not self.frames:
            return
        delay = self.frames[self.frame][1]
        self.accum += dt * 1000.0
        while self.accum >= delay:
            self.accum -= delay
            self.frame = (self.frame + 1) % len(self.frames)

    # ── 碰撞盒 ─────────────────────────────────────────────────────
    def rect(self) -> pygame.Rect:
        if self.frames:
            w, h = self.frames[self.frame][0].get_size()
        else:
            w, h = 30, 34
        ox, oy = self.origin
        # 脚底锚点 (x, cy)；sprite 左上角 = 锚点 - origin
        left = self.x - ox
        top = self.cy - oy
        return pygame.Rect(int(left), int(top), w, h)

    # ── 掉落（死亡时调用）──────────────────────────────────────────
    def roll_drop(self) -> Optional[dict]:
        if not self.drops:
            return None
        return random.choice(self.drops)

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, camera) -> None:
        if not self.frames:
            return
        frame_surf, _ = self.frames[self.frame]
        if self.hit_flash > 0 and int(self.hit_flash * 60) % 2 == 0:
            return
        # 朝向：美术默认朝左（未翻转），向右移动时水平翻转
        if self.dir > 0:
            frame_surf = pygame.transform.flip(frame_surf, True, False)
        # 锚点：脚底 = (x, cy)；origin 是帧内原点（脚底）相对左上角偏移
        sx, sy = camera.to_screen(self.x, self.cy)
        top_left = (sx - self.origin[0], sy - self.origin[1])
        surface.blit(frame_surf, (int(top_left[0]), int(top_left[1])))

    @property
    def sprite_w(self) -> int:
        return self.frames[self.frame][0].get_width() if self.frames else 30

    @property
    def sprite_h(self) -> int:
        return self.frames[self.frame][0].get_height() if self.frames else 34
