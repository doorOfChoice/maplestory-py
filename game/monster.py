"""怪物实体：从地图 life 数据生成，AI 状态机 巡逻 → 追击 → 接触攻击 → 受击 → 死亡。

坐标：(x, y) 为怪物脚底锚点（WZ life.cy 为地面 y），sprite 用 origin 偏移定位。
"""

from __future__ import annotations

import random
from typing import Optional, Tuple

import pygame

from . import settings
from .animation import Animation
from .assets import Assets


class Monster:
    def __init__(self, assets: Assets, data: dict, index: int,
                 physics=None):
        self.assets = assets
        self.mob_id = str(int(data["id"]))
        self.index = index
        self.x = float(data["x"])
        self.cy = float(data.get("cy") or data["y"])   # 地面接触 y
        self.rx0 = float(data["rx0"]) if data.get("rx0") is not None else float(data["x"])
        self.rx1 = float(data["rx1"]) if data.get("rx1") is not None else float(data["x"])
        self.flip = bool(data.get("flip"))

        # 脚底 foothold：巡逻/追击范围钳制到"出生段可沿链走到的同层平台"
        # 两端；怪物走到断口/高落差（超过一级台阶）时应在边界折返，
        # 而不是走出平台悬空或坠落。链内沿 prev/next 续段行走（跨台阶/坡道）。
        self.physics = physics
        self.fh = physics.surface_under(self.x, self.cy) if physics else None
        if self.fh is not None:
            roam_min, roam_max = self._reachable_bounds(self.fh)
            self.rx0 = max(self.rx0, roam_min + 6.0)
            self.rx1 = min(self.rx1, roam_max - 6.0)
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
        self.anim = Animation([], loop=True)
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
        if action == self.action and self.anim.frames:
            return
        self.action = action
        self.anim.frames = self.assets.mob_frames(self.mob_id, action)
        self.anim.loop = True
        self.anim.restart()
        self.origin = self.assets.mob_origin(self.mob_id, action) or (0, 0)

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
            self._resnap_ground()
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
            self.anim.advance(dt)
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
            self._step_move()          # 受击硬直期间仍贴地（击退后在平台上）
            self.anim.advance(dt)
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
            self._step_move()
            self._load_action("move" if self._has("move") else "stand")
        elif chasing and dist <= settings.MOB_ATTACK_RANGE:
            self.state = "attack"
            self._load_action("stand")
            self._step_move()
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
            self._step_move()
            self._load_action("move" if self._has("move") else "stand")

        self.anim.advance(dt)

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

    def _step_move(self) -> None:
        """沿脚下相连平台走：越过当前段端点时续接下一段，并跟随坡面高度。

        rx0/rx1 已被钳制在可步行平台内，故这里只会遇到"一级台阶内"的
        续段（自动走上走下）；若仍走到断口，则保持当前段高度，交由巡逻
        边界折返，绝不悬空或坠落。
        """
        if self.fh is None:
            return
        if not self.fh.covers(self.x):
            nxt = self.physics.walk_surface(self.fh, self.x, 0)
            if nxt is not None and nxt.covers(self.x):
                self.fh = nxt
            else:
                return
        self.cy = self.fh.y_at(self.x)

    def _resnap_ground(self) -> None:
        """受击击退后快速回到脚下段地面；只有确有支撑时才吸附，避免悬空。"""
        if self.fh is None:
            return
        if not self.fh.covers(self.x):
            nxt = self.physics.walk_surface(self.fh, self.x, 0)
            if nxt is not None and nxt.covers(self.x):
                self.fh = nxt
        if self.fh.covers(self.x):
            self.cy = self.fh.y_at(self.x)

    def _reachable_bounds(self, fh) -> Tuple[float, float]:
        """从出生段沿链向两端延伸，返回怪物可步行的同层平台水平范围。

        只接受"当前段边缘 → 下一水平段"高差在一级台阶内（可自动走上/
        走下）的连通段；遇到断口、高落差或开放边缘即停。如此把巡逻范围
        钳在怪物真正能站立的那块平台上，边界处折返而不是走出平台。

        :param fh: 出生时脚下的 foothold。
        """
        ph = self.physics
        xmin, xmax = fh.xmin, fh.xmax
        # 向右延伸
        f = fh
        while True:
            nxt = ph.linked_continuation(f, True)
            if nxt is None:
                break
            edge_x = f.xmax
            if abs(nxt.y_at(edge_x) - f.y_at(edge_x)) > settings.PLAYER_STEP_UP:
                break
            xmax = max(xmax, nxt.xmax)
            f = nxt
        # 向左延伸
        f = fh
        while True:
            nxt = ph.linked_continuation(f, False)
            if nxt is None:
                break
            edge_x = f.xmin
            if abs(nxt.y_at(edge_x) - f.y_at(edge_x)) > settings.PLAYER_STEP_UP:
                break
            xmin = min(xmin, nxt.xmin)
            f = nxt
        return xmin, xmax

    # ── 碰撞盒 ─────────────────────────────────────────────────────
    def rect(self) -> pygame.Rect:
        img = self.anim.surface
        if img is not None:
            w, h = img.get_size()
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
        frame_surf = self.anim.surface
        if frame_surf is None:
            return
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
        img = self.anim.surface
        return img.get_width() if img is not None else 30

    @property
    def sprite_h(self) -> int:
        img = self.anim.surface
        return img.get_height() if img is not None else 34