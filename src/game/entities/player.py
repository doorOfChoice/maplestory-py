"""玩家实体：输入 → 状态机 → 姿态动画 + foothold 物理。

世界坐标约定：y 向下为正，(x, y) 为角色 navel 锚点，脚底 = y + FEET_OFFSET。
朝向：flip=True 表示面向右（与 wzpy compose_animation 的 flip 语义一致）。
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pygame

from game import settings
from game.core import stats as stats_mod
from game.core import consumables
from game.core import skill_effects
from game.core.consumables import WarpFn
from game.core.animation import Animation
from game.render.assets import Assets
from game.core.buffs import BuffList, StatusList
from game.core.physics import Physics
from game.systems.inventory import Inventory, make_item
from game.core.jobs import JOBS, is_ranged_weapon
from game.systems.skills import SkillBook
from game.systems import skills as skills_mod
from game.core.stats import base_stats
from game.systems.quests import QuestLog
from game.core.motion import friction, JumpFeather

POSE_IDLE = "stand1"
POSE_RUN = "walk1"
POSE_JUMP = "jump"
POSE_LADDER = "ladder"
POSE_ROPE = "rope"
POSE_SWIM = "fly"        # 资产无 swim sprite，泳姿复用 fly


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
        self.attack_elapsed = 0.0
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
        self.contact_cooldown = 0.0   # 回避成功后接触冷却（不击退，仅防重复判定）
        # 跳跃手感：按压缓冲 + 土狼时间
        self.feather = JumpFeather(settings.JUMP_BUFFER_TIME,
                                   settings.COYOTE_TIME)

        if save_data is not None:
            self._apply_save_data(save_data, assets, quest_defs)
        else:
            self._init_new_game(assets, quest_defs)

        # 回程卷轴切图回调（Game 接线）：moveTo → None=成功 / str=拒绝原因
        self.on_warp: Optional[WarpFn] = None

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
        self.job = pd.get("job") or 0
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
        return stats_mod.exp_to_next(self.level)

    # ── 装备 / 属性 ────────────────────────────────────────────────
    def advance_to(self, code: int, assets: Assets) -> None:
        """转职：改 job → 累积重建技能树并保留旧转等级/SP → 附赠被动/快捷键 → 补发初始武器。"""
        jobdef = JOBS[code]
        old = self.skills
        self.job = code
        book = SkillBook(assets, code)
        book.inherit(old)                              # 累积：旧转技能与各转 SP 照带
        book.on_advance(jobdef)
        self.skills = book
        if jobdef.starter_weapon is not None:
            item = make_item(jobdef.starter_weapon, assets)
            if item.slot == "weapon" and self.inventory.equipped.get("weapon") is not None:
                if self.inventory.unequip("weapon"):   # 旧武器（出生木剑）回背包
                    self.inventory.equipped["weapon"] = item
                else:
                    self.inventory.add(item)
            elif item.slot is not None:
                self.inventory.equipped[item.slot] = item
        self.refresh_equips()

    def is_ranged(self) -> bool:
        """远程判定：手持弓/弩类武器（数据驱动，不绑定具体职业）。"""
        weapon = self.inventory.equipped.get("weapon")
        return weapon is not None and is_ranged_weapon(weapon.id)

    def refresh_equips(self) -> None:
        """装备栏变更后同步外观与派生数值（equips 列表驱动角色渲染）。"""
        self.equips = self.inventory.equip_ids()
        self.recalc_vitals()
        self._load_anim(POSE_IDLE if self.on_ground else POSE_JUMP)

    def _buff_mod(self, key: str, with_buffs: bool = True) -> int:
        """buff 词条求和；with_buffs=False 视同无 buff（详情弹窗取基础值用）。"""
        return self.buffs.mod_sum(key) if with_buffs else 0

    def _buff_rate(self, key: str, with_buffs: bool = True) -> float:
        """特效药百分比修正倍率：buff mods 的 pad/mad/... 之和 ÷100。"""
        return 1.0 + self._buff_mod(key, with_buffs) / 100.0

    def attack_value(self, with_buffs: bool = True) -> int:
        """物理攻击力（面板上限端）：(武器面板 × 主属性权重 + 被动/buff 加值) × 力藥%。"""
        pad = self.inventory.attack() or settings.BASE_WEAPON_PAD
        base = stats_mod.attack(self.total_stats(with_buffs), pad, self.is_ranged())
        flat = base + self.skills.passive_mods().get("atk", 0) \
            + self._buff_mod("atk", with_buffs)
        return int(flat * self._buff_rate("pad", with_buffs))

    def attack_range(self) -> Tuple[int, int]:
        """物理攻击区间 (min, max)：供战斗按 AyumiLove 公式结算。

        下限随武器熟练度（mastery 被动/buff）抬高；被动/buff 的平坦物攻两端同加，
        力藥（pad）按百分比乘在最后。
        """
        pad = self.inventory.attack() or settings.BASE_WEAPON_PAD
        lo, hi = stats_mod.attack_range(self.total_stats(), pad, self.is_ranged(),
                                        mastery=self.attack_mastery())
        bonus = self.skills.passive_mods().get("atk", 0) + self.buffs.mod_sum("atk")
        rate = self._buff_rate("pad")
        return max(1, int((lo + bonus) * rate)), max(1, int((hi + bonus) * rate))

    def attack_mastery(self) -> float:
        """武器熟练度（伤害下限比例）：默认 0.9 + 被动/buff mastery 百分点，封顶 1.0。"""
        points = self.skills.passive_mods().get("mastery", 0) \
            + self.buffs.mod_sum("mastery")
        return min(1.0, stats_mod.DEFAULT_MASTERY + points / 100.0)

    def attack_range_bonus(self) -> float:
        """射程加成（px）：被动（如百步穿楊）+ buff 的 range 词条。"""
        return float(self.skills.passive_mods().get("range", 0)
                     + self.buffs.mod_sum("range"))

    def crit_rate(self) -> float:
        """暴击率（%）：被动技能 + buff 的 crit 词条之和，封顶 100。"""
        return min(100.0, float(self.skills.passive_mods().get("crit", 0)
                                + self.buffs.mod_sum("crit")))

    def crit_mult(self) -> float:
        """暴击伤害倍率：被动/buff 取最强来源（如霸王箭 200→2.0），否则默认。"""
        best = self.skills.passive_mods().get("crit_mult", 0)
        best = max(best, self.buffs.mod_sum("crit_mult"))
        return best / 100.0 if best else settings.CRIT_MULT

    def _pure_buff_seconds(self, skill_data: dict) -> float:
        """技能若为纯 buff（非攻击）则返回其持续秒数，否则 0.0。

        判定统一走 skills.skill_buff_seconds（单一事实来源），再用于区分
        「扣消耗上 buff」与「进入攻击流程」。
        """
        d = skill_data.get("def")
        if d is None:
            return 0.0
        return skills_mod.skill_buff_seconds(d, int(skill_data.get("level", 0)))

    def _apply_buff_skill(self, skill_data: dict) -> bool:
        """纯 buff 技能接线：命中判定则上 buff 返回 True，否则 False。

        mods 由 core.skill_effects 按 WZ 字段语义翻译（通用字段 + 逐技能覆盖），
        平坦加值；未实装效果（如召唤/替身）会得到空 mods 但仍算施放成功。
        """
        seconds = self._pure_buff_seconds(skill_data)
        if seconds <= 0:
            return False
        d = skill_data["def"]
        lv = int(skill_data["level"])
        mods = skill_effects.buff_mods(
            str(skill_data["id"]), lambda key: d.stat(lv, key, 0))
        self.buffs.apply(str(skill_data["id"]), d.name, seconds, mods)
        return True

    def defense_value(self, with_buffs: bool = True) -> int:
        """物理防御力：(装备 PDD + DEX//10 + 被动/buff 加值) × 護甲藥%。"""
        flat = stats_mod.defense(self.total_stats(with_buffs),
                                 self.inventory.defense()) \
            + self.skills.passive_mods().get("def", 0) \
            + self._buff_mod("def", with_buffs)
        return int(flat * self._buff_rate("pdd", with_buffs))

    def magic_attack_value(self, with_buffs: bool = True) -> int:
        """面板魔法力（旧版 Magic）：总 INT + 装备 M.ATK + 被动/buff 魔攻，× 魔法藥%。

        法师伤害里 Magic 与技能 mad（Basic）是两个独立因子（见 magic_attack_range）。
        """
        stats = self.total_stats(with_buffs)
        magic = stats_mod.magic_attack(
            stats, self.inventory.stat_sum("incMAD")) \
            + self.skills.passive_mods().get("matk", 0) \
            + self._buff_mod("matk", with_buffs)
        return int(magic * self._buff_rate("mad", with_buffs))

    def magic_attack_range(self, skill_mad: int = 0, skill_mastery: int = 0,
                           with_buffs: bool = True) -> Tuple[int, int]:
        """法师伤害区间 (min, max)：旧版 Spell Damage。

        Magic = 面板魔法力（总 INT + 装备 M.ATK + 魔攻加成）；
        Basic = 技能 WZ mad（乘数）；mastery 只抬下限。
        熟练度 = 基础 MAGIC_BASE_MASTERY + (技能/被动/buff mastery 点) × 每点系数。
        """
        int_total = self.total_stats(with_buffs)["int"]
        points = skill_mastery + self.skills.passive_mods().get("mastery", 0) \
            + self._buff_mod("mastery", with_buffs)
        mastery = min(1.0, max(0.0, settings.MAGIC_BASE_MASTERY
                               + points * settings.MAGIC_MASTERY_PER_POINT))
        return stats_mod.magic_attack_range(
            int_total, self.magic_attack_value(with_buffs), skill_mad, mastery)

    def magic_defense_value(self, with_buffs: bool = True) -> int:
        """魔法防御：(装备 MDD 总和 + INT//10 + 被动/buff 魔防) × 護甲藥%。"""
        flat = stats_mod.magic_defense(self.total_stats(with_buffs),
                                       self.inventory.stat_sum("incMDD")) \
            + self.skills.passive_mods().get("mdef", 0) \
            + self._buff_mod("mdef", with_buffs)
        return int(flat * self._buff_rate("mdd", with_buffs))

    def physical_damage_reduce(self) -> int:
        """物理伤害减免 %（神之保护 buff）；仅对怪物接触/物理攻击生效。"""
        return max(0, self.buffs.mod_sum("dmg_reduce"))

    def accuracy_value(self, with_buffs: bool = True) -> int:
        """命中率：(基础 20 + DEX//2 + 装备 ACC + 被动/buff 平坦命中) × 命藥%。"""
        extra = self.skills.passive_mods().get("acc", 0) \
            + self._buff_mod("acc_flat", with_buffs)
        return int(stats_mod.accuracy(self.total_stats(with_buffs),
                                      self.inventory.stat_sum("incACC"), extra)
                   * self._buff_rate("acc", with_buffs))

    def evasion_value(self, with_buffs: bool = True) -> int:
        """回避率：(LUK//2 + 装备 EVA + 被动/buff 平坦回避) × 回避藥%。"""
        extra = self.skills.passive_mods().get("eva", 0) \
            + self._buff_mod("eva_flat", with_buffs)
        return int((stats_mod.evasion(self.total_stats(with_buffs),
                                      self.inventory.stat_sum("incEVA")) + extra)
                   * self._buff_rate("eva", with_buffs))

    def attack_speed_value(self) -> int:
        """攻击速度：武器 WZ speed 值（0 最快、越大越慢）；空手为 0。"""
        weapon = self.inventory.equipped.get("weapon")
        return weapon.stat("speed") if weapon is not None else 0

    def attack_anim_rate(self) -> float:
        """攻速 → 攻击动画推进倍率：delay=300+60×speed，基准 speed4 为 1.0。"""
        delay = settings.ATTACK_DELAY_BASE_MS \
            + self.attack_speed_value() * settings.ATTACK_DELAY_STEP_MS
        return settings.ATTACK_DELAY_REF_MS / delay

    def move_speed_display(self, with_buffs: bool = True) -> int:
        """移动速度（面板 %）：100 + 装备/被动/buff 加成折算。"""
        points = self.skills.passive_mods().get("speed", 0) \
            + self._buff_mod("speed", with_buffs)
        return int(100 * (1.0 + self._equip_speed_bonus("incSpeed")
                          + points / 100.0))

    def jump_power_display(self, with_buffs: bool = True) -> int:
        """跳跃力（面板 %）：100 + 装备/被动/buff 加成折算。"""
        points = self.skills.passive_mods().get("jump", 0) \
            + self._buff_mod("jump", with_buffs)
        return int(100 * (1.0 + self._equip_speed_bonus("incJump")
                          + points / 100.0))

    # ── 四维属性 ───────────────────────────────────────────────────
    def total_stats(self, with_buffs: bool = True) -> dict:
        """四维合计 = (加点 + 装备词条 + 被动 + buff 平坦) × (1 + stat_pct%)。"""
        inv = self.inventory
        passive = self.skills.passive_mods()
        pct = 1.0 + (passive.get("stat_pct", 0)
                     + self._buff_mod("stat_pct", with_buffs)) / 100.0
        return {k: int((self.stats.get(k, 0) + inv.bonus(k)
                        + passive.get(k, 0)
                        + self._buff_mod(k, with_buffs)) * pct)
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

    def _equip_speed_bonus(self, key: str) -> float:
        """装备 incSpeed/incJump 加成比例：WZ 以 0.1 点为单位存储（30=+3%），封顶见 settings。"""
        units = self.inventory.stat_sum(key)
        return min(units / 1000.0, settings.EQUIP_SPEED_BONUS_CAP)

    def move_speed(self) -> float:
        """地面水平速度：基础 × (1 + ΣincSpeed + (被动/速度藥)%)。"""
        points = self.skills.passive_mods().get("speed", 0) \
            + self.buffs.mod_sum("speed")
        return settings.MOVE_SPEED * (1.0 + self._equip_speed_bonus("incSpeed")
                                      + points / 100.0)

    def jump_velocity(self) -> float:
        """起跳初速度（负值）：基础 × (1 + ΣincJump + (被动/跳跃藥)%)。"""
        points = self.skills.passive_mods().get("jump", 0) \
            + self.buffs.mod_sum("jump")
        return settings.JUMP_VELOCITY * (1.0 + self._equip_speed_bonus("incJump")
                                         + points / 100.0)

    def mp_regen(self) -> float:
        """每秒 MP 自然回复：基础 + 被动「魔力恢復」加成（mod 单位 0.1/s）。"""
        bonus = self.skills.passive_mods().get("mp_regen", 0)
        return settings.SKILL_MP_REGEN + bonus * settings.MP_REGEN_MOD_SCALE

    def recalc_vitals(self) -> None:
        """按 等级/职业/装备 + 被动/buff 平坦 hp/mp 词条 重算上限，并将当前值钳入。"""
        jobdef = JOBS.get(self.job) or JOBS[0]
        inv = self.inventory
        passive = self.skills.passive_mods() if hasattr(self, "skills") else {}
        buffs = getattr(self, "buffs", None)
        hp_bonus = inv.bonus("hp") + passive.get("hp", 0) \
            + (buffs.mod_sum("hp") if buffs is not None else 0)
        mp_bonus = inv.bonus("mp") + passive.get("mp", 0) \
            + (buffs.mod_sum("mp") if buffs is not None else 0)
        self.max_hp = stats_mod.max_hp(self.level, jobdef.hp_gain, hp_bonus)
        self.max_mp = stats_mod.max_mp(self.level, jobdef.mp_gain, mp_bonus)
        self.hp = min(self.hp, self.max_hp)
        self.mp = min(self.mp, self.max_mp)

    def try_use_consume(self, item_id: str) -> Optional[str]:
        """使用消耗品（先验后扣）：成功返回 None，失败返回原因（供 flash）。"""
        return consumables.use(self, item_id)

    def use_item_by_id(self, item_id: str) -> bool:
        """使用指定消耗品（键位绑定的物品宏走这里）；结算恢复/传送效果。"""
        return self.try_use_consume(item_id) is None

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
            self.vy = self.jump_velocity() * 0.4
            self.feather.consume()
            return
        if self.attacking:
            return   # 攻击硬直中不起跳（原地挥击）
        if self.in_water and not self.on_ground:
            # 水中划水：跳跃键给一次向上冲量（不是起跳初速度）
            self.vy = -settings.SWIM_JUMP_SPEED
            self.feather.consume()
            return
        if self.on_ground or self.feather.coyote > 0.0:
            self.vy = self.jump_velocity()
            self.on_ground = False
            self.feather.consume()
            return
        if self.wall_dir and not self.attacking and self.hurt_timer <= 0:
            # 蹬墙跳：反向弹开 + 向上，短暂失控期内屏蔽朝原墙方向的输入
            d = self.wall_dir
            self.vy = self.jump_velocity()
            self.vx = -d * settings.WALL_JUMP_VX
            self.facing_right = d < 0
            self.wall_dir = 0
            self.wall_side = d
            self.wall_lock = settings.WALL_JUMP_LOCK
            self.feather.consume()

    def teleport(self, distance: float, physics: Optional[Physics],
                 up: bool = False, down: bool = False,
                 direction: int = 0) -> bool:
        """快速移动：朝按下的方向键瞬移 distance px，落点必定吸附到平台。

        direction 为水平方向（1 右 / -1 左 / 0 不水平）；up/down 为垂直方向，
        优先于水平。未给任何方向则原地不动（由施放流程保证一定有方向）。
        水平：沿 foothold 链接以极小步长推进（爬坡/下坡随地形起伏），被实墙
        挡住即停在墙外；终点必须落到平台上——先就近吸附（同高/链接），否则取
        范围内最近平台落下（更高或更低都算），找不到则不触发，绝不以悬空结束。
        垂直：↑/↓ 找 range 内最近的平台落下；range 内无平台则原地不动
        （不穿墙、不掉出世界）。
        地面按「最近」判定，与 layer 无关：链可在 layer 间穿行，同高的前后景
        平台同样是可行走面（与行走语义一致）。落点会把 ground_layer 同步到
        所站平台，墙体碰撞随之切换。
        挂在绳/梯上（climbing）时不可瞬移，直接返回 False。
        返回是否成功位移（供施放流程决定是否扣 MP/写冷却）。
        """
        if physics is None or distance <= 0 or self.climbing:
            return False
        feet = self.y + settings.FEET_OFFSET
        if up or down:
            fh = physics.teleport_vertical_surface(self.x, feet, distance,
                                                   up=up)
            if fh is None:
                return False
            self._teleport_land(fh)
            # 竖直落点无「来向」，按最近侧把身体推出台阶 riser 等实墙外
            self.x = physics.deembed_walls(self.x, self.feet_y, fh.layer)
        elif direction:
            if not self._teleport_walk(distance, physics, direction):
                return False
            self.facing_right = direction > 0
        else:
            return False
        self.vx = 0.0
        self.drop_layers.clear()
        if not self.attacking:
            self._load_anim(POSE_IDLE if self.on_ground else POSE_JUMP)
        return True

    def _teleport_walk(self, distance: float, physics: Physics,
                       direction: int) -> bool:
        """水平瞬移：朝 direction（1 右 / -1 左）以极小步长推进到 distance 处。

        逐段沿 foothold 链接「走」过去（含楼梯/斜坡，脚随地形起伏），脱离链接
        后继续水平推进并在终点找落点；路径上被实墙挡住就停在墙外。步长很小，
        既不埋进上升坡体，也不会被墙豁免规则送进墙里（落点再用 wall_overlap_clamp
        兜底）。终点必须落在平台上：先就近吸附（同高容差 / 链接续段），否则在
        终点取 distance 内最近的平台落下（更高或更低都算）。找不到落点则返回
        False、原地不动（不掉出世界、不以悬空结束）。"""
        target = self.x + direction * distance
        x = self.x
        feet = self.y + settings.FEET_OFFSET
        fh = self.cur_fh
        grounded = self.on_ground and fh is not None
        layer = fh.layer if grounded else self.ground_layer
        max_step = 4.0
        guard = int(abs(distance) / max_step) + 4
        while guard > 0 and abs(target - x) > 0.5:
            guard -= 1
            step = direction * min(max_step, abs(target - x))
            nx = x + step
            bx = physics.wall_block(x, nx, feet, feet,
                                    fh if grounded else None, layer=layer)
            if direction * (bx - x) <= 1e-6:
                x = bx                                 # 撞墙：贴到墙面外
                break
            nx = bx
            if grounded:
                surf = physics.walk_surface(fh, nx, direction)
                if surf is None:
                    grounded = False
                else:
                    fh = surf
                    layer = surf.layer
                    feet = surf.y_at(nx)
            if not grounded:
                snap = physics.spawn_surface(
                    nx, feet, tol=settings.TELEPORT_SNAP_TOL)
                if snap is not None:
                    grounded = True
                    fh = snap
                    layer = snap.layer
                    feet = snap.y_at(nx)
            x = nx
        # 落点贴地 → 以真实脚高再推离一次墙（途中脚高可能与落点不同），
        # 推离后地面可能变，故最多迭代几次直到既不嵌墙又有地面。
        for _ in range(3):
            if grounded and fh is not None:
                surf = physics.walk_surface(fh, x, 0)
                if surf is None:
                    surf = physics.spawn_surface(
                        x, feet, tol=settings.TELEPORT_SNAP_TOL)
            else:
                surf = None
            if surf is None:
                break
            feet = surf.y_at(x)
            cx = physics.wall_overlap_clamp(x, feet, direction, surf.layer)
            if abs(cx - x) <= 1e-6:
                self.x = x
                self._teleport_land(surf)
                return True
            x = cx
            fh = surf
            grounded = True
        # 未就近吸附到平台：在终点取 distance 内最近的平台落下（更远/更高的
        # 平台也算），确保瞬移必定以站在平台上结束；实在找不到则原地不动。
        surf = physics.nearest_surface_in_range(x, feet, distance)
        if surf is not None:
            self.x = x
            self._teleport_land(surf)
            self.x = physics.wall_overlap_clamp(self.x, self.feet_y,
                                                direction, surf.layer)
            return True
        return False

    def _teleport_land(self, fh) -> None:
        """瞬移落点吸附到平台：脚贴面、清竖直速度、重置地面状态。"""
        self.y = fh.y_at(self.x) - settings.FEET_OFFSET
        self.cur_fh = fh
        self.on_ground = True
        self.ground_layer = fh.layer
        self.vy = 0.0

    def drop_through(self, physics: Optional[Physics] = None) -> None:
        if self.in_water:
            return   # 水中没有「下跳穿平台」语义
        if self.on_ground and self.cur_fh is not None:
            # 下方没有其他平台时不允许下跳（如底层主路），否则会掉出地图
            if physics is not None:
                feet = self.feet_y
                has_below = any(
                    not f.is_wall and f.covers(self.x)
                    and f.y_at(self.x) > feet + 4.0
                    for f in physics.footholds
                )
                if not has_below:
                    return
            self.drop_layers.add(self.cur_fh.layer)
            self.drop_timer = settings.DROP_THROUGH_TIME
            self.on_ground = False
            self.vy = 60.0

    def attack_slot_free(self, for_skill: bool = False) -> bool:
        """攻击槽是否可用：未在攻击中；技能施放（for_skill）还可取消已结算普攻的后摇。

        结算点 = 近战命中已应用 / 远程弹道已生成（伤害在起手帧完成，
        之后的动画纯属后摇）。取消规则对齐原版手感与平衡：
        普攻不可互取消（攻速由动画决定）；技能可取消普攻后摇，
        但技能动画（含技能接技能）必须完整播完，防止双技交替变相提速。
        例外：通道技（repeat，如暴風神射）不受上一条限制——按住连发的
        节奏由补放间隔决定，若等上一发后摇播完，间隔会被动画吞掉变慢速单发。
        """
        if self.hurt_timer > 0 or self.statuses.locked():
            return False
        if not self.attacking:
            return True
        if (for_skill and self.pending_skill is not None
                and self.pending_skill.get("repeat")):
            return True
        if not for_skill or self.pending_skill is not None:
            return False
        settled = self.attack_hit_applied or self.attack_projectile_spawned
        return settled and self.attack_elapsed >= settings.ATTACK_CANCEL_DELAY

    def _attack_pose_for(self, skill_data: Optional[dict]) -> str:
        """本次出手的姿态：技能 WZ action（法师 alert2 等）优先，否则回退武器攻击姿态。

        action 是官方为该技能声明的施法动作名；只有角色身体确实含该姿态时才用，
        避免无该动作的职业/武器拿到空帧。
        """
        action = (skill_data or {}).get("action")
        if action and self.assets.character_frames(
                self.equips, action, self.facing_right):
            return action
        return self.assets.attack_pose(self.equips)

    def start_attack(self, skill_data: Optional[dict] = None) -> bool:
        """发起攻击；skill_data 非空时为技能攻击（先扣 MP/HP 消耗）。

        buff 技能（level 表含 time）不进入攻击：扣消耗后直接上 buff。
        挂在绳/梯上时只允许施放纯 buff（非攻击）技能，普攻与攻击技能均被拒。
        """
        if not self.attack_slot_free(for_skill=skill_data is not None):
            return False
        if self.climbing and (skill_data is None
                              or self._pure_buff_seconds(skill_data) <= 0):
            return False
        if skill_data is not None:
            if (self.mp < skill_data["mp_con"]
                    or self.hp <= skill_data["hp_con"]):
                return False
            self.mp -= skill_data["mp_con"]
            self.hp = max(1, self.hp - skill_data["hp_con"])
            if self._apply_buff_skill(skill_data):
                return True
            self.pending_skill = skill_data
        else:
            self.pending_skill = None
        self.attacking = True
        self.attack_pose = self._attack_pose_for(skill_data)
        self.attack_hit_applied = False
        self.attack_projectile_spawned = False
        self.attack_timer = 3.0
        self.attack_elapsed = 0.0
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
            self.skills.gain_sp_for_level(self.level, settings.SP_PER_LEVEL)
            leveled = True
        return leveled

    def add_levels(self, count: int) -> None:
        """GM 加等级：直接升 N 级（不填经验），补 AP/SP/上下限并回满。
        每级重算上限并回满；升级可跨过转职等级，不校验职业门槛。"""
        for _ in range(max(0, count)):
            self.level += 1
            self.ap += settings.AP_PER_LEVEL
            self.recalc_vitals()
            self.hp = self.max_hp
            self.mp = self.max_mp
            self.skills.gain_sp_for_level(self.level, settings.SP_PER_LEVEL)

    def damage(self, amount: int) -> None:
        self.hp = max(0, self.hp - amount)

    def take_attack_damage(self, amount: int) -> Tuple[int, int]:
        """受到怪物攻击：按魔法盾（magic_guard%）把伤害转扣 MP，MP 不足回落 HP。

        返回 (实际扣 HP, 实际扣 MP)。仅怪物接触/技能伤害走此入口；坠落、中毒
        等环境伤害仍直接走 damage()，不受魔法盾影响。
        """
        pct = min(100, max(0, self.buffs.mod_sum("magic_guard")))
        redirect = int(amount * pct / 100.0)
        mp_pay = min(int(self.mp), redirect)
        self.mp -= mp_pay
        hp_dmg = amount - mp_pay
        self.damage(hp_dmg)
        return hp_dmg, mp_pay

    def is_invulnerable(self) -> bool:
        """是否处于接触免疫（受击无敌闪烁，或回避成功后的接触冷却）。"""
        return self.invuln_timer > 0 or self.contact_cooldown > 0

    def on_dodge(self) -> None:
        """回避成功：进入接触冷却，期间怪物接触不再判定（不击退/不硬直）。"""
        self.contact_cooldown = settings.MISS_COOLDOWN

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

        # 受击硬直 / 无敌 / 回避冷却计时
        if self.invuln_timer > 0:
            self.invuln_timer -= dt
        if self.contact_cooldown > 0:
            self.contact_cooldown -= dt
        if self.hurt_timer > 0:
            self.hurt_timer -= dt

        # 技能冷却 / MP 自然回复
        self.skills.tick(dt)
        if self.mp < self.max_mp:
            self.mp = min(self.max_mp, self.mp + self.mp_regen() * dt)

        # buff / 状态异常计时（中毒本帧伤害直接扣血）
        self.buffs.tick(dt)
        poison_dmg = self.statuses.tick(dt)
        if poison_dmg:
            self.damage(poison_dmg)

        # 攻击结束回 idle（带超时保险，防止动画状态卡死无法再次攻击）
        if self.attacking:
            self.attack_timer -= dt
            self.attack_elapsed += dt
            done = self._tick_frame(dt * self.attack_anim_rate(),
                                    loop=False) or self.attack_timer <= 0
            if done:
                self.attacking = False
                self.pending_skill = None
                self._load_anim(POSE_IDLE if self.on_ground else POSE_JUMP)
        else:
            self._tick_frame(dt, loop=True)

        # 水中且离地：走泳态分支（无重力 / 8 向游动 / fly 姿态）；
        # 一旦落到水底/平台（on_ground）则走常规步行逻辑，角色恢复站立/行走。
        if self.in_water and not self.on_ground:
            self._update_swim(dt, keys, physics)
            return

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
            # 攻击期间保留进入攻击时的水平速度（惯性）但不响应方向键加速，
            # 按摩擦逐渐衰减到停 —— 原版挥击时「边走边砍、最后定住」的手感。
            self.vx = friction(self.vx, dt, settings.ATTACK_MOVE_FRICTION)
        elif self.statuses.locked():
            self.stop_move()
        elif self.hurt_timer > 0:
            # 击退滑行，按距离衰减
            self.vx *= max(0.0, 1 - 6.0 * dt)
        elif push_back_to_wall:
            pass    # 蹬墙跳失控期：保持弹开速度，方向输入先不抵消
        else:
            # 原版行为：按方向当帧满速、松手立停、空中转向不打折。
            target_vx = 0.0
            if keys.left and not keys.right:
                target_vx = -self.move_speed()
                self.facing_right = False
            elif keys.right and not keys.left:
                target_vx = self.move_speed()
                self.facing_right = True
            target_vx *= self.statuses.speed_mult()
            # 同向且已有更高动量（蹬墙弹开等）时保留，不被打回基础走速
            if target_vx * self.vx > 0 and abs(self.vx) > abs(target_vx):
                pass
            else:
                self.vx = target_vx

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
                # 钉在绳/梯中心线上：挂绳瞬间吸附，攀爬中不被水平输入带偏
                self.x = physics.rope_center_x(ladder)
                self.vx = 0.0
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

        # 落地检测：下落（vy>=0）用垂直穿线带；上升帧只跑沿迹重接
        # （击退大横位移插进坡体时坡面抬升快过穿线，须即时接回）
        if self.on_ground:
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
                    self.x, prev_feet, now_feet, self.drop_layers,
                    prev_x=prev_x)
            if surf is not None:
                self.y = surf.y_at(self.x) - settings.FEET_OFFSET
                self.cur_fh = surf
                self.vy = 0.0
                self.drop_layers.discard(surf.layer)
            else:
                self.on_ground = False
                self.cur_fh = None
        else:
            fh = physics.landing_candidate(self.x, prev_feet, now_feet,
                                           self.drop_layers, prev_x=prev_x,
                                           band=self.vy >= 0)
            if fh is not None:
                self.y = fh.y_at(self.x) - settings.FEET_OFFSET
                self.vy = 0.0
                self.on_ground = True
                self.cur_fh = fh
                self.drop_layers.discard(fh.layer)

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

    def _update_swim(self, dt: float, keys, physics: Physics) -> None:
        """水图泳态：无重力、8 向游动；水平仍挡墙，下沉碰到水底即贴住但保持泳姿。

        方向键只驱动水平与下潜；上浮由跳跃键的一次向上冲量给出（见
        :meth:`_try_jump`），↑ 在水中不产生任何作用。松手水平滑停、
        竖直缓慢下沉探底（原版「松手缓慢滑停」的手感）。
        """
        self.on_ground = False
        self.cur_fh = None
        self.climbing = False
        self.wall_dir = 0
        self.wall_lock = 0.0
        self.ground_layer = None

        if self.attacking:
            self.vx = friction(self.vx, dt, settings.ATTACK_MOVE_FRICTION)
            self.vy = friction(self.vy, dt, settings.ATTACK_MOVE_FRICTION)
        elif self.statuses.locked():
            self.stop_move()
            self.vy = 0.0
        elif self.hurt_timer > 0:
            self.vx *= max(0.0, 1 - 6.0 * dt)
            self.vy *= max(0.0, 1 - 6.0 * dt)
        else:
            dx = (1 if keys.right and not keys.left
                  else -1 if keys.left and not keys.right else 0)
            dy = 1 if keys.down else 0    # 上浮只由跳跃键的冲量驱动，↑ 在水中无效
            if dx:
                self.facing_right = dx > 0
            if dx or dy:
                length = math.hypot(dx, dy)
                self.vx = dx / length * settings.SWIM_SPEED
                if dy:
                    self.vy = dy / length * settings.SWIM_SPEED
                else:
                    # 只有水平输入时不清零纵向速度：保留跳跃冲量并缓慢衰减，
                    # 否则「边横向游动边按跳跃」会把向上冲量抹成 0。
                    self.vy += (settings.SWIM_SINK_SPEED - self.vy) * min(
                        1.0, settings.SWIM_DRAG * dt)
            else:
                self.vx = friction(self.vx, dt, settings.SWIM_DRAG)
                self.vy += (settings.SWIM_SINK_SPEED - self.vy) * min(
                    1.0, settings.SWIM_DRAG * dt)

        prev_x = self.x
        prev_feet = self.y + settings.FEET_OFFSET
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.x = physics.wall_block(prev_x, self.x, prev_feet,
                                    self.y + settings.FEET_OFFSET,
                                    self.cur_fh, layer=self.ground_layer)
        now_feet = self.y + settings.FEET_OFFSET

        # 下沉碰到水底 foothold：落到水底转入常规步行（站立/行走），不再游泳
        if self.vy > 0:
            fh = physics.landing_candidate(self.x, prev_feet, now_feet,
                                           prev_x=prev_x)
            if fh is not None:
                self.y = fh.y_at(self.x) - settings.FEET_OFFSET
                self.vy = 0.0
                self.on_ground = True
                self.cur_fh = fh
                self.ground_layer = fh.layer
        # 兜底：无 foothold 时钳在水图 VR 底边，避免沉出地图（仍在水中悬浮）
        bounds = getattr(self.assets, "bounds", None)
        if bounds:
            bottom = float(bounds["bottom"]) - settings.FEET_OFFSET
            if self.y > bottom:
                self.y = bottom
                self.vy = 0.0

        if not self.attacking and not self.on_ground:
            self._switch_if_needed(POSE_SWIM)

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
    def in_water(self) -> bool:
        """当前地图是否为整图水域（WZ info/swim=1）。"""
        return bool(getattr(self.assets, "swim", False))

    @property
    def feet_y(self) -> float:
        return self.y + settings.FEET_OFFSET

    # ── 攻击命中框（相对 navel，朝向方向）────────────────────────
    def attack_rect(self) -> Optional[pygame.Rect]:
        if not self.attacking:
            return None
        bonus = self.attack_range_bonus()
        rng = settings.ATTACK_RANGE + bonus
        if self.pending_skill is not None and self.pending_skill["range"] > 0:
            # 技能范围以玩家为中心（如剑气纵横 range 130），再叠加被动射程
            rng = float(self.pending_skill["range"]) + bonus
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
