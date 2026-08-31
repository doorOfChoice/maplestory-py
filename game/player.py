"""玩家实体：输入 → 状态机 → 姿态动画 + foothold 物理。

世界坐标约定：y 向下为正，(x, y) 为角色 navel 锚点，脚底 = y + FEET_OFFSET。
朝向：flip=True 表示面向右（与 wzpy compose_animation 的 flip 语义一致）。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import pygame

from . import settings
from .assets import Assets
from .physics import Physics
from .inventory import Inventory, make_item
from .skills import SkillBook

POSE_IDLE = "stand1"
POSE_RUN = "walk1"
POSE_JUMP = "jump"
POSE_LADDER = "ladder"
POSE_ROPE = "rope"


class Player:
    def __init__(self, assets: Assets, spawn_x: float, spawn_y: float,
                 equips: Optional[List[str]] = None):
        self.assets = assets
        self.equips = equips or settings.DEFAULT_EQUIPS
        self.x = float(spawn_x)
        self.y = float(spawn_y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.cur_fh = None
        # 生效 layer：站立平台的层；空中沿用最后所站层（墙阻挡/贴墙用）
        self.ground_layer: Optional[int] = None

        self.facing_right = True
        self.pose = POSE_IDLE
        self.frame = 0
        self.accum = 0.0
        self.frames: List[Tuple[pygame.Surface, int]] = []
        self.navel_px = (0, 0)

        # 状态
        self.attacking = False
        self.attack_pose = ""
        self.attack_hit_applied = False
        self.attack_timer = 0.0       # 攻击状态超时保险，防止动画状态卡死
        self.climbing = False
        self.detach_cooldown = 0.0    # 从绳上跳下后的短暂时间，防止立刻重新吸附
        self.wall_dir = 0             # 本帧贴着的墙方向（-1 左墙 / +1 右墙 / 0 无）
        self.wall_lock = 0.0          # 蹬墙跳后短暂失控计时
        self.wall_side = 0            # 蹬开的那面墙方向（失控期内仍按它屏蔽输入）
        self.anim_flip = self.facing_right
        self.drop_layers = set()      # 下跳要忽略的 layer
        self.drop_timer = 0.0
        self.hurt_timer = 0.0         # 受击硬直：期间锁移动/攻击，击退自然衰减
        self.invuln_timer = 0.0       # 受击无敌：期间闪烁且不再吃伤害

        # 属性
        self.hp = settings.PLAYER_MAX_HP
        self.max_hp = settings.PLAYER_MAX_HP
        self.mp = settings.PLAYER_MAX_MP
        self.max_mp = settings.PLAYER_MAX_MP
        self.level = 1
        self.exp = 0

        # 背包 / 装备 / 技能
        self.inventory = Inventory()
        for item_id, count in settings.START_CONSUMES.items():
            self.inventory.add(make_item(item_id, assets, count))
        # 初始穿戴：默认外观里的装备（武器/衣/裤/鞋）进装备栏
        for eid in settings.DEFAULT_EQUIPS[4:]:
            item = make_item(eid, assets)
            if item.slot is not None:
                self.inventory.equipped[item.slot] = item
        self.skills = SkillBook(assets)
        self.pending_skill: Optional[dict] = None   # 本次攻击使用的技能数据
        self.refresh_equips()

        self._load_anim(POSE_IDLE)

    # ── 动画 ───────────────────────────────────────────────────────
    def _load_anim(self, pose: str, flip: Optional[bool] = None) -> None:
        if flip is None:
            flip = self.facing_right
        self.pose = pose
        self.anim_flip = flip
        self.frames = self.assets.character_frames(self.equips, pose, flip)
        self.navel_px = self.assets.character_navel_px(self.equips, pose, flip)
        self.frame = 0
        self.accum = 0.0

    def exp_to_next(self) -> int:
        return int(settings.BASE_EXP_NEED * (settings.EXP_GROWTH ** (self.level - 1)))

    # ── 装备 / 属性 ────────────────────────────────────────────────
    def refresh_equips(self) -> None:
        """装备栏变更后同步外观（equips 列表驱动角色渲染）。"""
        self.equips = self.inventory.equip_ids()
        self._load_anim(POSE_IDLE if self.on_ground else POSE_JUMP)

    def attack_value(self) -> int:
        """物理攻击力：基础成长 + 武器等装备 incPAD。"""
        return 10 + self.level * 2 + self.inventory.attack() * 3

    def defense_value(self) -> int:
        """物理防御力：等级成长 + 防具 incPDD。"""
        return self.level * 2 + self.inventory.defense()

    def use_potion(self) -> bool:
        """快捷喝药：优先 HP 药水，其次 MP 药水。返回是否使用成功。"""
        order = sorted(self.inventory.consumes.values(),
                       key=lambda i: 0 if i.info.get("spec", {}).get("hp") else 1)
        for item in order:
            spec = item.info.get("spec") or {}
            if not spec:
                continue
            spec = self.inventory.use_consume(item.id)
            if not spec:
                continue
            hp = int(spec.get("hp") or 0)
            mp = int(spec.get("mp") or 0)
            if hp:
                self.hp = min(self.max_hp, self.hp + hp)
            if mp:
                self.mp = min(self.max_mp, self.mp + mp)
            return True
        return False

    # ── 控制 ───────────────────────────────────────────────────────
    def move_left(self) -> None:
        self.vx = -settings.MOVE_SPEED
        self.facing_right = False

    def move_right(self) -> None:
        self.vx = settings.MOVE_SPEED
        self.facing_right = True

    def stop_move(self) -> None:
        self.vx = 0.0

    def jump(self) -> None:
        if self.climbing:
            # 从绳/梯上跳下：向上小跳（JUMP_VELOCITY 本身为负）
            self.climbing = False
            self.detach_cooldown = 0.20
            self.vy = settings.JUMP_VELOCITY * 0.4
            return
        if self.on_ground:
            self.vy = settings.JUMP_VELOCITY
            self.on_ground = False
        elif self.wall_dir and not self.attacking and self.hurt_timer <= 0:
            # 蹬墙跳：反向弹开 + 向上，短暂失控期内屏蔽朝原墙方向的输入
            d = self.wall_dir
            self.vy = settings.JUMP_VELOCITY
            self.vx = -d * settings.WALL_JUMP_VX
            self.facing_right = d < 0
            self.wall_dir = 0
            self.wall_side = d
            self.wall_lock = settings.WALL_JUMP_LOCK

    def drop_through(self, physics: Optional[Physics] = None) -> None:
        if self.on_ground and self.cur_fh is not None:
            # 下方没有其他平台时不允许下跳（如底层主路），否则会掉出地图
            if physics is not None:
                feet = self.feet_y
                has_below = any(
                    f.x1 != f.x2 and f.covers(self.x)
                    and f.y_at(self.x) > feet + 4.0
                    for f in physics.footholds
                )
                if not has_below:
                    return
            self.drop_layers.add(self.cur_fh.layer)
            self.drop_timer = settings.DROP_THROUGH_TIME
            self.on_ground = False
            self.vy = 60.0

    def start_attack(self, skill_data: Optional[dict] = None) -> bool:
        """发起攻击；skill_data 非空时为技能攻击（先扣 MP/HP 消耗）。"""
        if self.attacking or self.hurt_timer > 0:
            return False
        if skill_data is not None:
            if (self.mp < skill_data["mp_con"]
                    or self.hp <= skill_data["hp_con"]):
                return False
            self.mp -= skill_data["mp_con"]
            self.hp = max(1, self.hp - skill_data["hp_con"])
            self.pending_skill = skill_data
        else:
            self.pending_skill = None
        self.attacking = True
        self.attack_pose = self.assets.attack_pose(self.equips)
        self.attack_hit_applied = False
        self.attack_timer = 3.0
        self._load_anim(self.attack_pose)
        return True

    def gain_exp(self, amount: int) -> bool:
        """增加经验，返回是否升级。"""
        self.exp += amount
        leveled = False
        while self.exp >= self.exp_to_next():
            self.exp -= self.exp_to_next()
            self.level += 1
            self.max_hp += 12
            self.max_mp += 6
            self.hp = self.max_hp
            self.mp = self.max_mp
            self.skills.gain_sp(settings.SP_PER_LEVEL)
            leveled = True
        return leveled

    def damage(self, amount: int) -> None:
        self.hp = max(0, self.hp - amount)

    def hurt(self, from_x: float) -> bool:
        """被怪物击中：击退小跳 + 硬直 + 短暂无敌。无敌期间忽略伤害。"""
        if self.invuln_timer > 0:
            return False
        self.invuln_timer = settings.HURT_INVULN
        self.hurt_timer = settings.HURT_STUN
        away = 1 if self.x >= from_x else -1
        self.climbing = False
        self.vx = away * settings.HURT_KNOCKBACK
        self.vy = min(self.vy, settings.HURT_HOP_VY)   # 原版的小弹跳
        self.on_ground = False
        return True

    # ── 每帧更新 ───────────────────────────────────────────────────
    def update(self, dt: float, keys, physics: Physics, audio=None) -> None:
        # 下跳计时
        if self.drop_timer > 0:
            self.drop_timer -= dt
            if self.drop_timer <= 0:
                self.drop_layers.clear()

        # 受击硬直 / 无敌计时
        if self.invuln_timer > 0:
            self.invuln_timer -= dt
        if self.hurt_timer > 0:
            self.hurt_timer -= dt

        # 技能冷却 / MP 自然回复
        self.skills.tick(dt)
        if self.mp < self.max_mp:
            self.mp = min(self.max_mp, self.mp + settings.SKILL_MP_REGEN * dt)

        # 攻击结束回 idle（带超时保险，防止动画状态卡死无法再次攻击）
        if self.attacking:
            self.attack_timer -= dt
            done = self._tick_frame(dt, loop=False) or self.attack_timer <= 0
            if done:
                self.attacking = False
                self.pending_skill = None
                self._load_anim(POSE_IDLE if self.on_ground else POSE_JUMP)
        else:
            self._tick_frame(dt, loop=True)

        # 水平移动输入（攻击/受击硬直过程中不能主动移动）
        if self.wall_lock > 0:
            self.wall_lock -= dt
            if self.wall_lock <= 0:
                self.wall_side = 0
        push_back_to_wall = self.wall_side != 0 and self.wall_lock > 0 and (
            (self.wall_side > 0 and keys.right and not keys.left)
            or (self.wall_side < 0 and keys.left and not keys.right))
        if self.attacking:
            self.stop_move()
        elif self.hurt_timer > 0:
            # 击退滑行，按距离衰减
            self.vx *= max(0.0, 1 - 6.0 * dt)
        elif push_back_to_wall:
            pass    # 蹬墙跳失控期：保持弹开速度，方向输入先不抵消
        elif keys.left and not keys.right:
            self.move_left()
        elif keys.right and not keys.left:
            self.move_right()
        else:
            self.stop_move()

        # 爬梯/爬绳（含细绳）
        ladder = physics.rope_at(self.x, self.y)
        up = keys.up and (not keys.down)
        down = keys.down and (not keys.up)
        if self.detach_cooldown > 0:
            self.detach_cooldown -= dt
        if ladder is not None and up and not self.climbing \
                and self.detach_cooldown <= 0:
            self.climbing = True
        if self.climbing:
            if ladder is None:
                self.climbing = False
            else:
                landed = False
                if up:
                    self.y -= settings.LADDER_SPEED * dt
                    # 到顶：绳顶附近找可站立的上沿平台，直接爬上去。
                    # 只在 navel 接近绳顶时判定，途中穿过的平台不会打断爬绳
                    if self.y <= ladder["y1"] + 6.0:
                        fh = physics.top_landing(self.x, self.y + settings.FEET_OFFSET)
                        if fh is not None:
                            self.y = fh.y_at(self.x) - settings.FEET_OFFSET
                            self.vy = 0.0
                            self.on_ground = True
                            self.cur_fh = fh
                            self.climbing = False
                            landed = True
                        elif self.y < ladder["y1"] - settings.CLIMB_TOP_OVERSHOOT:
                            # 顶端没有平台：钳在越出上限，避免脱离→坠落→重吸死循环
                            self.y = ladder["y1"] - settings.CLIMB_TOP_OVERSHOOT
                elif down:
                    prev_c = self.y + settings.FEET_OFFSET
                    self.y += settings.LADDER_SPEED * dt
                    now_c = self.y + settings.FEET_OFFSET
                    # 到底：脚越过绳底附近的地面时落地
                    fh = physics.landing_candidate(self.x, prev_c, now_c)
                    if fh is not None and fh.y_at(self.x) >= ladder["y2"] - 12.0:
                        self.y = fh.y_at(self.x) - settings.FEET_OFFSET
                        self.vy = 0.0
                        self.on_ground = True
                        self.cur_fh = fh
                        self.climbing = False
                        landed = True
                if not landed and self.climbing:
                    self.vy = 0.0
                    self.on_ground = False
                    if not self.attacking:
                        climb_pose = (POSE_LADDER if ladder.get("ladder")
                                      else POSE_ROPE)
                        if not self.frames or self.pose not in (POSE_LADDER, POSE_ROPE) \
                                or self.pose != climb_pose:
                            try:
                                self._load_anim(climb_pose)
                            except Exception:
                                self._switch_if_needed(POSE_LADDER)
                    return
                # landed → 落到下方常规物理/姿态逻辑

        # 物理：重力 + 位移
        prev_feet = self.y + settings.FEET_OFFSET
        prev_x = self.x
        if self.cur_fh is not None:
            self.ground_layer = self.cur_fh.layer
        # 贴墙下滑：空中压着贴着墙那一侧的方向键下落 → 限速（蹬墙跳的窗口）
        sliding = (self.wall_dir != 0 and not self.on_ground
                   and not self.climbing and self.vy > 0
                   and ((self.wall_dir > 0 and keys.right and not keys.left)
                        or (self.wall_dir < 0 and keys.left and not keys.right)))
        self.vy += settings.GRAVITY * dt
        cap = settings.WALL_SLIDE_SPEED if sliding else settings.MAX_FALL_SPEED
        if self.vy > cap:
            self.vy = cap
        self.x += self.vx * dt
        self.y += self.vy * dt
        # 竖直墙水平阻挡：只挡"自己 layer"的墙（他层为前后景，可穿行）；
        # 传入当前链使"链接的一级台阶"可以走上去而非被拦
        self.x = physics.wall_block(prev_x, self.x, prev_feet,
                                    self.y + settings.FEET_OFFSET,
                                    self.cur_fh, layer=self.ground_layer)
        now_feet = self.y + settings.FEET_OFFSET

        # 落地检测（下落时穿过某条线段）
        if self.vy >= 0 and not self.on_ground:
            fh = physics.landing_candidate(self.x, prev_feet, now_feet, self.drop_layers)
            if fh is not None:
                self.y = fh.y_at(self.x) - settings.FEET_OFFSET
                self.vy = 0.0
                self.on_ground = True
                self.cur_fh = fh
                self.drop_layers.discard(fh.layer)
        elif self.on_ground:
            # 贴坡只认"当前链"：cur_fh 覆盖脚下 → 跟坡插值；越过端点 →
            # 仅接受 prev/next 链接的一级台阶续段。前景坡/悬垂平台等
            # 无链接的邻近面不参与贴坡（原版行走=沿 foothold 链游走）。
            direction = (1 if self.vx > 0.5
                         else -1 if self.vx < -0.5 else 0)
            surf = physics.walk_surface(self.cur_fh, self.x, direction,
                                        self.drop_layers)
            if surf is None and self.cur_fh is None:
                surf = physics.grounded_surface(self.x, now_feet)
            if surf is None:
                # 大步长（如切窗回来 dt 尖峰）会瞬时沉到容差之外：
                # 同帧用穿线检测兜底找回地面，避免误判成坠落而穿透
                surf = physics.landing_candidate(
                    self.x, prev_feet, now_feet, self.drop_layers)
            if surf is not None:
                self.y = surf.y_at(self.x) - settings.FEET_OFFSET
                self.cur_fh = surf
                self.vy = 0.0
                self.drop_layers.discard(surf.layer)
            else:
                self.on_ground = False
                self.cur_fh = None

        # 贴墙状态刷新（供下一帧的贴墙下滑 / 蹬墙跳使用）
        self.wall_dir = 0
        if (not self.on_ground and not self.climbing and self.wall_lock <= 0
                and not self.attacking and self.hurt_timer <= 0):
            if keys.right and not keys.left:
                press = 1
            elif keys.left and not keys.right:
                press = -1
            else:
                press = 0
            if press and physics.touching_wall(self.x, now_feet, press,
                                               layer=self.ground_layer) is not None:
                self.wall_dir = press

        # 姿态选择（非攻击时）
        if not self.attacking:
            if not self.on_ground:
                self._switch_if_needed(POSE_JUMP)
            elif abs(self.vx) > 1.0:
                self._switch_if_needed(POSE_RUN)
            else:
                self._switch_if_needed(POSE_IDLE)

    def _switch_if_needed(self, pose: str) -> None:
        if self.pose != pose or self.anim_flip != self.facing_right:
            self._load_anim(pose)

    def _tick_frame(self, dt: float, loop: bool) -> bool:
        """推进动画帧。非循环姿态播完返回 True（已回到首帧）。"""
        if not self.frames:
            return False
        delay = self.frames[self.frame][1]
        self.accum += dt * 1000.0
        wrapped = False
        while self.accum >= delay:
            self.accum -= delay
            if not loop and self.frame >= len(self.frames) - 1:
                self.frame = 0
                self.accum = 0.0
                wrapped = True
                break
            self.frame = (self.frame + 1) % len(self.frames)
        return wrapped

    @property
    def _animation_done(self) -> bool:
        return False

    @property
    def feet_y(self) -> float:
        return self.y + settings.FEET_OFFSET

    # ── 攻击命中框（相对 navel，朝向方向）────────────────────────
    def attack_rect(self) -> Optional[pygame.Rect]:
        if not self.attacking:
            return None
        rng = settings.ATTACK_RANGE
        if self.pending_skill is not None and self.pending_skill["range"] > 0:
            # 技能范围以玩家为中心（如劍氣縱橫 range 130）
            rng = float(self.pending_skill["range"])
            left = self.x - rng / 2
        elif self.facing_right:
            left = self.x
        else:
            left = self.x - rng
        top = self.y - settings.ATTACK_HEIGHT / 2
        return pygame.Rect(int(left), int(top), int(rng), int(settings.ATTACK_HEIGHT))

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, camera) -> None:
        if not self.frames:
            return
        # 无敌期间闪烁（原版受击后的半透明忽隐忽现）
        if self.invuln_timer > 0 and int(self.invuln_timer * 12) % 2 == 0:
            return
        frame_surf, _ = self.frames[self.frame]
        sx, sy = camera.to_screen(self.x, self.y)
        top_left = (sx - self.navel_px[0], sy - self.navel_px[1])
        surface.blit(frame_surf, (int(top_left[0]), int(top_left[1])))
