"""玩家实体：输入 → 状态机 → 姿态动画 + foothold 物理。

世界坐标约定：y 向下为正，(x, y) 为角色 navel 锚点，脚底 = y + FEET_OFFSET。
朝向：flip=True 表示面向右（与 wzpy compose_animation 的 flip 语义一致）。
"""

from __future__ import annotations

from typing import List, Optional

import pygame

from . import settings
from . import stats as stats_mod
from .animation import Animation
from .assets import Assets
from .buffs import BuffList, StatusList
from .physics import Physics
from .inventory import Inventory, make_item
from .jobs import JOBS, is_ranged_weapon
from .skills import SkillBook
from .stats import base_stats
from .quests import QuestLog
from .motion import approach, JumpFeather

POSE_IDLE = "stand1"
POSE_RUN = "walk1"
POSE_JUMP = "jump"
POSE_LADDER = "ladder"
POSE_ROPE = "rope"


class Player:
    def __init__(self, assets: Assets, spawn_x: float, spawn_y: float,
                 equips: Optional[List[str]] = None, quest_defs=None,
                 save_data: Optional[dict] = None):
        self.assets = assets
        self.equips = equips or settings.DEFAULT_EQUIPS
        self.x = float(spawn_x)
        self.y = float(spawn_y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.cur_fh = None
        self.ground_layer: Optional[int] = None

        self.facing_right = True
        self.pose = POSE_IDLE
        self.anim = Animation([], loop=True)
        self.navel_px = (0, 0)

        self.job = 0
        self.attacking = False
        self.attack_pose = ""
        self.attack_hit_applied = False
        self.attack_projectile_spawned = False
        self.attack_timer = 0.0
        self.climbing = False
        self.detach_cooldown = 0.0
        self.wall_dir = 0
        self.wall_lock = 0.0
        self.wall_side = 0
        self.anim_flip = self.facing_right
        self.drop_layers = set()
        self.drop_timer = 0.0
        self.hurt_timer = 0.0
        self.invuln_timer = 0.0
        # 跳跃手感：按压缓冲 + 土狼时间
        self.feather = JumpFeather(settings.JUMP_BUFFER_TIME,
                                   settings.COYOTE_TIME)

        if save_data is not None:
            self._apply_save_data(save_data, assets, quest_defs)
        else:
            self._init_new_game(assets, quest_defs)

        # buff / 状态异常（不入库：死亡与重登清空，同原版）
        self.buffs = BuffList()
        self.statuses = StatusList()

        self._load_anim(POSE_IDLE)

    def _init_new_game(self, assets: Assets, quest_defs) -> None:
        """新游戏初始化：预设属性、初始药水、预设装备、技能初始赠送。"""
        self.hp = self.mp = 0
        self.level = 1
        self.exp = 0
        self.stats = base_stats()
        self.ap = 0
        self.inventory = Inventory()
        for item_id, count in settings.START_CONSUMES.items():
            self.inventory.add(make_item(item_id, assets, count))
        for eid in settings.DEFAULT_EQUIPS[4:]:
            item = make_item(eid, assets)
            if item.slot is not None:
                self.inventory.equipped[item.slot] = item
        self.skills = SkillBook(assets, self.job)
        self.pending_skill: Optional[dict] = None
        self.refresh_equips()
        self.quests = QuestLog(quest_defs or {})
        self.recalc_vitals()
        self.hp = self.max_hp
        self.mp = self.max_mp

    def _apply_save_data(self, data: dict, assets: Assets, quest_defs) -> None:
        """从存档 dict 恢复玩家状态。"""
        pd = data["player"]
        self.level = pd["level"]
        self.exp = pd["exp"]
        self.hp = pd["hp"]
        self.max_hp = pd["max_hp"]
        self.mp = pd["mp"]
        self.max_mp = pd["max_mp"]
        self.job = pd.get("job", 0)
        self.stats = dict(pd.get("stats") or base_stats())
        self.ap = int(pd.get("ap") or 0)
        self.facing_right = pd.get("facing_right", True)
        self.anim_flip = self.facing_right

        self.inventory = Inventory.from_dict(data.get("inventory", {}), assets)
        self.skills = SkillBook(assets, self.job)
        self.skills.from_dict(data.get("skills", {}))
        self.pending_skill = None
        self.refresh_equips()
        self.quests = QuestLog(quest_defs or {})
        self.quests.from_dict(data.get("quests", {}))
        self.recalc_vitals()

    # ── 动画 ───────────────────────────────────────────────────────
    def _load_anim(self, pose: str, flip: Optional[bool] = None) -> None:
        if flip is None:
            flip = self.facing_right
        self.pose = pose
        self.anim_flip = flip
        frames = self.assets.character_frames(self.equips, pose, flip)
        self.anim = Animation(frames, loop=True)
        self.navel_px = self.assets.character_navel_px(self.equips, pose, flip)

    def exp_to_next(self) -> int:
        return int(settings.BASE_EXP_NEED * (settings.EXP_GROWTH ** (self.level - 1)))

    # ── 装备 / 属性 ────────────────────────────────────────────────
    def advance_to(self, code: int, assets: Assets) -> None:
        """转职：改 job → 重建职业技能树 + 附赠被动/快捷键 → 补发初始武器。"""
        jobdef = JOBS[code]
        self.job = code
        self.skills = SkillBook(assets, code)
        self.skills.on_advance(jobdef)
        if jobdef.starter_weapon is not None:
            item = make_item(jobdef.starter_weapon, assets)
            if item.slot is not None and self.inventory.equipped.get("weapon") is None:
                self.inventory.equipped[item.slot] = item
            elif item.slot is not None:
                self.inventory.add(item)   # 已持其他武器：短弓入背包
        self.refresh_equips()

    def is_ranged(self) -> bool:
        """远程职业且手持弓/弩。"""
        weapon = self.inventory.equipped.get("weapon")
        return (self.job == settings.BOWMAN_JOB and weapon is not None
                and is_ranged_weapon(weapon.id))

    def refresh_equips(self) -> None:
        """装备栏变更后同步外观与派生数值（equips 列表驱动角色渲染）。"""
        self.equips = self.inventory.equip_ids()
        self.recalc_vitals()
        self._load_anim(POSE_IDLE if self.on_ground else POSE_JUMP)

    def attack_value(self) -> int:
        """物理攻击力：武器面板 × 主属性权重 + 副属性/10 + 被动/buff 加值。"""
        pad = self.inventory.attack() or settings.BASE_WEAPON_PAD
        base = stats_mod.attack(self.total_stats(), pad, self.is_ranged())
        return base + self.skills.passive_mods().get("atk", 0) \
            + self.buffs.mod_sum("atk")

    def defense_value(self) -> int:
        """物理防御力：装备 PDD 总和 + DEX//10 + 被动/buff 加值。"""
        return stats_mod.defense(self.total_stats(), self.inventory.defense()) \
            + self.skills.passive_mods().get("def", 0) \
            + self.buffs.mod_sum("def")

    # ── 四维属性 ───────────────────────────────────────────────────
    def total_stats(self) -> dict:
        """四维合计 = 加点属性 + 装备词条 + 被动技能 + buff（str/dex/int/luk）。"""
        inv = self.inventory
        passive = self.skills.passive_mods()
        return {k: self.stats.get(k, 0) + inv.bonus(k)
                + passive.get(k, 0) + self.buffs.mod_sum(k)
                for k in stats_mod.STAT_KEYS}

    @property
    def luk(self) -> int:
        return self.total_stats()["luk"]

    def allocate_ap(self, stat: str, n: int = 1) -> bool:
        """手动加点：成功返回 True 并刷新 HP/MP 上限。"""
        new_stats, new_ap = stats_mod.allocate(self.stats, self.ap, stat, n)
        if new_ap == self.ap and new_stats == self.stats:
            return False
        self.stats, self.ap = new_stats, new_ap
        self.recalc_vitals()
        return True

    def auto_allocate_ap(self) -> bool:
        """一键自动分配：按职业权重投完所有 AP。"""
        jobdef = JOBS.get(self.job) or JOBS[0]
        new_stats, new_ap = stats_mod.auto_allocate(
            self.stats, self.ap, jobdef.auto_ap)
        if new_ap == self.ap and new_stats == self.stats:
            return False
        self.stats, self.ap = new_stats, new_ap
        self.recalc_vitals()
        return True

    def recalc_vitals(self) -> None:
        """按 等级/职业/装备词条 重算 HP/MP 上限，并把当前值钳进上限。"""
        jobdef = JOBS.get(self.job) or JOBS[0]
        inv = self.inventory
        self.max_hp = stats_mod.max_hp(self.level, jobdef.hp_gain, inv.bonus("hp"))
        self.max_mp = stats_mod.max_mp(self.level, jobdef.mp_gain, inv.bonus("mp"))
        self.hp = min(self.hp, self.max_hp)
        self.mp = min(self.mp, self.max_mp)

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
    def stop_move(self) -> None:
        self.vx = 0.0

    def jump(self) -> None:
        # 记录跳跃意图（缓冲），供 update 在可跳时机（含土狼窗口）执行。
        self.feather.press()
        self._try_jump()

    def _try_jump(self) -> None:
        """在地面 / 土狼窗口 / 绳梯 / 蹬墙 的跳。成功则清空缓冲避免重复起跳。"""
        if self.statuses.locked():
            return
        if self.climbing:
            # 从绳/梯上跳下：向上小跳（JUMP_VELOCITY 本身为负）
            self.climbing = False
            self.detach_cooldown = 0.20
            self.vy = settings.JUMP_VELOCITY * 0.4
            self.feather.consume()
            return
        if self.attacking:
            return   # 攻击硬直中不起跳（原地挥击）
        if self.on_ground or self.feather.coyote > 0.0:
            self.vy = settings.JUMP_VELOCITY
            self.on_ground = False
            self.feather.consume()
            return
        if self.wall_dir and not self.attacking and self.hurt_timer <= 0:
            # 蹬墙跳：反向弹开 + 向上，短暂失控期内屏蔽朝原墙方向的输入
            d = self.wall_dir
            self.vy = settings.JUMP_VELOCITY
            self.vx = -d * settings.WALL_JUMP_VX
            self.facing_right = d < 0
            self.wall_dir = 0
            self.wall_side = d
            self.wall_lock = settings.WALL_JUMP_LOCK
            self.feather.consume()

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
        if self.attacking or self.hurt_timer > 0 or self.statuses.locked():
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
        self.attack_projectile_spawned = False
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
            self.ap += settings.AP_PER_LEVEL
            self.recalc_vitals()
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

        # buff / 状态异常计时（中毒本帧伤害直接扣血）
        self.buffs.tick(dt)
        poison_dmg = self.statuses.tick(dt)
        if poison_dmg:
            self.damage(poison_dmg)

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

        # 跳跃手感：推进缓冲/土狼窗口，并在可跳（缓冲内 & 地面/土狼窗口）时重试起跳。
        # 顺序放在输入之前：落地前一瞬按跳 → 缓冲保留 → 落地这帧立即接上，按键跟手。
        self.feather.tick(dt, self.on_ground)
        if self.feather.buffered:
            self._try_jump()

        if self.attacking:
            self.stop_move()
        elif self.statuses.locked():
            self.stop_move()
        elif self.hurt_timer > 0:
            # 击退滑行，按距离衰减
            self.vx *= max(0.0, 1 - 6.0 * dt)
        elif push_back_to_wall:
            pass    # 蹬墙跳失控期：保持弹开速度，方向输入先不抵消
        else:
            # 水平缓动：地面快、空中按 AIR_ACCEL 打折扣 → 柔化起停（丝滑的关键）。
            target_vx = 0.0
            if keys.left and not keys.right:
                target_vx = -settings.MOVE_SPEED
                self.facing_right = False
            elif keys.right and not keys.left:
                target_vx = settings.MOVE_SPEED
                self.facing_right = True
            target_vx *= self.statuses.speed_mult()
            accel = settings.MOVE_ACCEL
            if not self.on_ground:
                accel *= settings.AIR_ACCEL
            self.vx = approach(self.vx, target_vx, accel * dt)

        # 爬梯/爬绳（含细绳）
        ladder = physics.rope_at(self.x, self.y)
        up = keys.up and (not keys.down)
        down = keys.down and (not keys.up)
        if self.detach_cooldown > 0:
            self.detach_cooldown -= dt
        # 站上/经过绳梯即按 ↑ 或 ↓ 都可开始攀爬（原版：顶端按↓直接下滑）。
        # 但已站上绳顶平台时按↑不重新挂绳（避免顶上来回振荡），↓ 随时可下。
        at_rope_top = (self.on_ground and self.cur_fh is not None
                       and ladder is not None
                       and self.feet_y <= float(ladder["y1"]) + 6.0)
        if ladder is not None and (up or down) and not self.climbing \
                and self.detach_cooldown <= 0 and not (up and at_rope_top):
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
                        if not self.anim.frames or self.pose not in (POSE_LADDER, POSE_ROPE) \
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
        self.anim.loop = loop
        return self.anim.advance(dt)

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
            # 技能范围以玩家为中心（如剑气纵横 range 130）
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
        frame_surf = self.anim.surface
        if frame_surf is None:
            return
        # 无敌期间闪烁（原版受击后的半透明忽隐忽现）
        if self.invuln_timer > 0 and int(self.invuln_timer * 12) % 2 == 0:
            return
        sx, sy = camera.to_screen(self.x, self.y)
        top_left = (sx - self.navel_px[0], sy - self.navel_px[1])
        surface.blit(frame_surf, (int(top_left[0]), int(top_left[1])))
