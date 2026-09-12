"""战斗：攻击判定、伤害飘字、掉落物、经验/升级。

Game 主循环持有 Combat，负责：
  · 玩家攻击命中框 vs 怪物碰撞盒 → 伤害、击退、掉落、经验
  · 怪物接触伤害 → 玩家扣血
  · 伤害飘字动画与绘制
  · 掉落物生成 / 拾取
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Protocol, Set, Tuple

import pygame

from game import settings
from game.core import stats as stats_mod
from game.core.animation import Animation
from game.core.combat_log import CombatLog
from game.core.equip_roll import roll_drop_bonus
from game.render.assets import Assets
from game.render.effects import Effect
from game.systems.drops import OfficialDropTable, load_official_table
from game.systems.inventory import make_item
from game.systems.scrolls import is_scroll_id
from game.core.fonts import render_text


class Combatant(Protocol):
    """攻击方（Player）在伤害结算链路中暴露的最小「数值契约」。

    战斗只依赖这套接口计算伤害，不关心 Player 的其它实现细节；
    可注入假对象，便于脱离实体的单元测试与后续 DI。
    """
    x: float
    y: float
    facing_right: bool
    level: int

    @property
    def luk(self) -> int: ...

    def attack_range(self) -> Tuple[int, int]: ...
    def crit_rate(self) -> float: ...
    def crit_mult(self) -> float: ...
    def accuracy_value(self) -> int: ...
    def attack_rect(self) -> Optional[pygame.Rect]: ...


class CombatTarget(Protocol):
    """可被攻击的实体（Monster / 合成怪物）所需接口。"""
    x: float
    cy: float
    sprite_h: float
    pd: int
    mdd: int
    eva: int
    level: int
    dead: bool

    def rect(self) -> pygame.Rect: ...
    def take_hit(self, damage: int, from_x: Optional[float] = None) -> bool: ...


def roll_damage(base: int) -> int:
    """伤害浮动：基础值 ±10%，最低 1。"""
    return max(1, int(round(base * random.uniform(0.9, 1.1))))


class DamageNumber:
    """官方样式伤害飘字：Effect.wz/BasicEff.img 的 NoRed/NoViolet/NoBlue 像素数字。

    动画照原版：前 400ms 原地全亮，后 600ms 上升 30px 并线性淡出，总寿命 1s。
    伤害 ≥1000 用大号数字集（NoXxx1），0 伤害显示 Miss。
    """

    KIND_SETS = {"red": "NoRed", "violet": "NoViolet", "blue": "NoBlue"}
    # 官方 Miss 字形只在 NoRed0 / NoViolet0 的小号集里（NoBlue 各集无此字形），
    # 故 0 伤害一律回退 NoRed0，避免蓝字 MISS 取不到贴图而整条不显示。
    MISS_SET = "NoRed0"
    FONT = None
    HOLD = 0.4            # 原地停留时长（秒）
    FADE = 0.6            # 上升淡出时长（秒）
    RISE_PX = 30.0        # 淡出期间上升距离

    def __init__(self, x: float, y: float, amount: int, kind: str = "red",
                 big: bool = False):
        self.x = x
        self.y = y
        self.amount = amount
        self.kind = kind
        self.big = big          # 暴击：强制用大号数字集（NoViolet1）
        self.elapsed = 0.0

    @property
    def set_name(self) -> str:
        if self.amount <= 0:
            return self.MISS_SET
        base = self.KIND_SETS.get(self.kind, "NoRed")
        return base + ("1" if (self.big or self.amount >= 1000) else "0")

    @property
    def digits(self) -> List[str]:
        if self.amount <= 0:
            return ["Miss"]
        return list(str(self.amount))

    @property
    def alpha(self) -> float:
        t = self.elapsed - self.HOLD
        if t <= 0.0:
            return 1.0
        return max(0.0, 1.0 - t / self.FADE)

    @property
    def rise(self) -> float:
        t = self.elapsed - self.HOLD
        if t <= 0.0:
            return 0.0
        return min(self.RISE_PX, self.RISE_PX * t / self.FADE)

    def update(self, dt: float) -> bool:
        self.elapsed += dt
        return self.elapsed < self.HOLD + self.FADE

    def draw(self, surface: pygame.Surface, camera, assets=None) -> None:
        sx, sy = camera.to_screen(self.x, self.y - self.rise)
        sprites = assets.damage_digits(self.set_name) if assets else {}
        if not sprites:      # 素材缺失退回字体渲染
            if DamageNumber.FONT is None:
                DamageNumber.FONT = pygame.font.Font(None, 24)
            color = {"violet": (170, 120, 255), "blue": (120, 180, 255)}.get(
                self.kind, (255, 60, 60))
            text = render_text(DamageNumber.FONT, str(self.amount or "Miss"), color)
            surface.blit(text, (int(sx - text.get_width() / 2), int(sy)))
            return
        pieces = [sprites.get(d) for d in self.digits]
        if any(p is None for p in pieces):
            return
        total_w = sum(p[0].get_width() for p in pieces)
        px = int(sx - total_w / 2)
        fade = self.alpha < 1.0
        for surf, origin in pieces:
            if fade:
                surf = self._faded(surf, self.alpha)
            surface.blit(surf, (px - origin[0], int(sy) - origin[1]))
            px += surf.get_width()

    @staticmethod
    def _faded(surf: pygame.Surface, fade: float) -> pygame.Surface:
        """逐像素乘 alpha 淡出，返回副本（不改动缓存表面）。

        不能用 Surface.set_alpha(int)：对 SRCALPHA 表面其行为未定义，真实显示
        驱动下会用统一 alpha 覆盖逐像素 alpha，使数字外围本应透明的背景整块变
        实色（黑条）。这里用 BLEND_RGBA_MULT 只缩放 alpha 通道。
        """
        faded = surf.copy()
        mod = pygame.Surface(faded.get_size(), pygame.SRCALPHA)
        mod.fill((255, 255, 255, max(0, min(255, int(255 * fade)))))
        faded.blit(mod, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return faded


class DropItem:
    """掉落物：金币（官方硬币旋转动画）或物品（官方 info/icon 图标）。"""

    def __init__(self, x: float, y: float, item: Optional[dict] = None,
                  meso: int = 0, ground_y: Optional[float] = None,
                  assets: Optional[Assets] = None,
                  lifetime: Optional[float] = None, pickup_lock: float = 0.0,
                  from_mob: bool = True):
        self.x = x
        self.y = y
        self.item = item
        self.meso = int(meso)
        self.assets = assets
        self.life = settings.DROP_LIFETIME if lifetime is None else lifetime
        self.pickup_lock = pickup_lock   # 生成后短暂不可拾取（玩家扔出防瞬间捡回）
        self.from_mob = from_mob         # 怪物掉落才随机基础属性；玩家扔出的不随机
        self.vx = random.uniform(-30, 30)
        self.vy = -120.0
        self.taken = False
        self.name = item.get("name") if item else f"{self.meso} 金币"
        # 落地基准：脚下 foothold 的表面（略微抬高让图形贴地），缺省用生成点
        self.ground_y = (ground_y if ground_y is not None
                         else y) - 4.0
        self._age = 0.0
        # 吸附动画状态（拾取后物品飞向角色）
        self.attracting = False
        self._attract_tx = 0.0
        self._attract_ty = 0.0
        self._attract_elapsed = 0.0

    @property
    def is_meso(self) -> bool:
        return self.item is None

    def update(self, dt: float, px: float = 0.0, py: float = 0.0) -> bool:
        self._age += dt
        if self.attracting:
            self._attract_elapsed += dt
            dx = self._attract_tx - self.x
            dy = self._attract_ty - self.y
            dist = (dx * dx + dy * dy) ** 0.5
            t = min(self._attract_elapsed / settings.PICKUP_ATTRACT_TIME, 1.0)
            ease = t * t * (3.0 - 2.0 * t)  # smoothstep
            speed = 800.0 * ease
            if dist > 2.0:
                self.x += dx / dist * speed * dt
                self.y += dy / dist * speed * dt
            self.y -= 4.0 * dt  # 轻微上浮弧线
            self.life -= dt
            return self.life > 0 and dist > 2.0 and self._attract_elapsed < settings.PICKUP_ATTRACT_TIME * 1.5
        self.life -= dt
        self.vy += settings.GRAVITY * 0.35 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        # 落地弹跳（衰减）
        if self.y >= self.ground_y and self.vy > 0:
            self.y = self.ground_y
            self.vy = -abs(self.vy) * 0.3
            if abs(self.vy) < 12:
                self.vy = 0.0
        # 在地面上时水平摩擦减速
        if self.vy == 0.0:
            self.vx *= max(0.0, 1 - 6.0 * dt)
        return self.life > 0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 8), int(self.y - 8), 16, 16)

    def _sprite(self) -> Optional[pygame.Surface]:
        if self.is_meso:
            frames = self.assets.meso_frames(self.meso) if self.assets else []
            if frames:
                idx = Animation.frame_at(frames, self._age * 1000)
                return frames[idx][0]
            return None
        if self.item is not None and self.assets is not None:
            iid = self.item.get("id")
            if is_scroll_id(iid):
                from game.render.windows.core.widgets import scroll_icon
                return scroll_icon()    # 234 段自制卷轴：统一自绘图标
            s = self.assets.item_icon(iid)
            if s is None:
                s = self.assets.equip_icon(iid)
            return s
        return None

    def draw(self, surface: pygame.Surface, camera) -> None:
        sx, sy = camera.to_screen(self.x, self.y)
        img = self._sprite()
        if img is not None:
            w, h = img.get_size()
            if self.attracting:
                t = min(self._attract_elapsed / settings.PICKUP_ATTRACT_TIME, 1.0)
                scale = 1.0 + 0.25 * t
                sw, sh = int(w * scale), int(h * scale)
                scaled = pygame.transform.scale(img, (sw, sh))
                surface.blit(scaled, (int(sx - sw / 2), int(sy - sh / 2)))
            else:
                surface.blit(img, (int(sx - w / 2), int(sy - h / 2)))
            return
        # 图标缺失时的占位（如装备不在本 WZ 子集）
        pygame.draw.circle(surface, (255, 220, 80), (int(sx), int(sy)), 5)
        pygame.draw.circle(surface, (255, 255, 220), (int(sx - 1), int(sy - 1)), 2)


class Arrow:
    """远程弹道实体：直线快箭（无重力）+ 穿透计数。

    命中结算在飞行中进行：与未命中过的怪 rect 相交 → 伤害 + 飘字 + hit 特效；
    累计命中数达 mobCount、寿命耗尽或出界即消失。
    """

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 frames: list, hit_frames: list, dmg: int,
                 mob_count: int = 1, life: float = 0.6,
                 crit: bool = False,
                 atk_lo: Optional[int] = None, atk_hi: Optional[int] = None,
                 mult: float = 1.0, crit_rate: float = 0.0,
                 crit_mult: float = settings.CRIT_MULT, player_level: int = 0,
                 attack_count: int = 1, magic: bool = False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.frames = frames            # [(Surface, origin, delay_ms)]
        self.hit_frames = hit_frames
        self.dmg = dmg                  # 固定伤害（无 atk 参数直构 Arrow 时用）+ 预览
        self.mob_count = max(1, mob_count)
        self.life = life
        self.crit = crit
        # 命中时按近战同一公式结算（stats.roll_damage）：逐目标/逐段 roll，
        # 吃等级差与怪防、每段独立暴击；atk_lo=None 时退回固定 dmg/crit。
        self.atk_lo = atk_lo
        self.atk_hi = atk_hi
        self.mult = mult
        self.crit_rate = crit_rate
        self.crit_mult = crit_mult
        self.player_level = player_level
        self.attack_count = max(1, attack_count)
        self.magic = magic                # 魔法攻击改用怪 mdd 而非 pd 减伤
        self.age = 0.0
        self.hit_ids: set = set()
        self.dead = False
        self._flipped: Optional[list] = None
        self._rot_cache: dict = {}

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 6), int(self.y - 6), 12, 12)

    def _roll(self, mob, rng) -> Tuple[int, bool]:
        """本次命中伤害；有攻击参数走统一公式，否则用固定 dmg/crit。"""
        if self.atk_lo is None:
            return self.dmg, self.crit
        mob_pd = mob.mdd if self.magic else mob.pd
        return stats_mod.roll_damage(
            self.atk_lo, self.atk_hi, self.mult, mob_pd,
            self.player_level, mob.level, rng,
            self.crit_rate, self.crit_mult)

    def update(self, dt: float, monsters, combat, player=None) -> None:
        if self.dead:
            return
        self.life -= dt
        self.age += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        for mob in monsters:
            if mob.dead or id(mob) in self.hit_ids:
                continue
            if not self.rect().colliderect(mob.rect()):
                continue
            self.hit_ids.add(id(mob))
            missed = player is not None and combat.rng.random() >= \
                stats_mod.hit_chance(player.accuracy_value(), mob.eva,
                                     player.level - mob.level)
            if missed:
                combat.numbers.append(DamageNumber(
                    mob.x, mob.cy - mob.sprite_h, 0))
            else:
                if self.hit_frames:
                    combat.effects.append(Effect(
                        self.hit_frames, mob.x,
                        mob.cy - mob.sprite_h * 0.45,
                        use_origin=True,
                        flip=self.vx > 0))
                combat.preferred_mob = mob
                for _ in range(self.attack_count):
                    dmg, crit = self._roll(mob, combat.rng)
                    combat.numbers.append(DamageNumber(
                        mob.x, mob.cy - mob.sprite_h, dmg,
                        "violet" if crit else "red", big=crit))
                    died = mob.take_hit(dmg, from_x=self.x)
                    if died:
                        if player is not None:
                            combat._on_kill(player, mob)
                        break
            if len(self.hit_ids) >= self.mob_count:
                self.dead = True
                return
        if self.life <= 0:
            self.dead = True

    def draw(self, surface: pygame.Surface, camera) -> None:
        if not self.frames:
            return
        if abs(self.vy) > 1e-6:
            # 斜射弹道：贴图按速度方向旋转（角度量化缓存）。
            # 素材朝左（基准 180°），换算应转的角度 = 目标角 - 180°。
            idx = Animation.frame_at(self.frames, self.age * 1000.0)
            img, _, _ = self.frames[idx]
            deg = math.degrees(math.atan2(-self.vy, self.vx)) - 180.0
            q = int(round(deg / 5.0) * 5)
            key = (idx, q)
            rot = self._rot_cache.get(key)
            if rot is None:
                rot = pygame.transform.rotate(img, q)
                self._rot_cache[key] = rot
            sx, sy = camera.to_screen(self.x, self.y)
            surface.blit(rot, rot.get_rect(center=(int(sx), int(sy))))
            return
        frames = self.frames
        if self.vx > 0:
            if self._flipped is None:
                self._flipped = [
                    (pygame.transform.flip(s, True, False),
                     (s.get_width() - 1 - ox, oy), d)
                    for s, (ox, oy), d in frames]
            frames = self._flipped
        idx = Animation.frame_at(frames, self.age * 1000.0)
        img, origin, _ = frames[idx]
        sx, sy = camera.to_screen(self.x, self.y)
        surface.blit(img, (int(sx - origin[0]), int(sy - origin[1])))


class Combat:
    def __init__(self, assets: Assets,
                 drop_table: Optional[OfficialDropTable] = None,
                 rng: Optional[random.Random] = None):
        self.assets = assets
        self.drop_table = drop_table if drop_table is not None \
            else load_official_table()
        self.rng = rng if rng is not None else random
        self.numbers: List[DamageNumber] = []
        self.drops: List[DropItem] = []
        self.effects: List[object] = []      # 命中火花 / 升级特效等
        self.arrows: List[Arrow] = []        # 飞行中的远程弹道
        self.meso = 0                        # 拾取的金币
        self.total_kills = 0
        self.pending_exp: List[int] = []
        self.combat_log = CombatLog()        # 右下角战斗明细（击杀/拾取）
        self.preferred_mob = None            # 集火目标：上一只被打到的怪（防误引）

    def _surface_y(self, x: float, ref_y: float) -> Optional[float]:
        """x 处与 ref_y 最接近的 foothold 表面 y（dict 数据，无 Foothold 对象）。"""
        best: Optional[float] = None
        best_d = 30.0
        for f in self.assets.footholds:
            x1, x2 = f["x1"], f["x2"]
            if x1 == x2 or not (min(x1, x2) - 1.0 <= x <= max(x1, x2) + 1.0):
                continue
            y = f["y1"] + (f["y2"] - f["y1"]) * (x - x1) / (x2 - x1)
            d = abs(y - ref_y)
            if d <= best_d:
                best, best_d = y, d
        return best

    def _drop_ground(self, x: float, ref_y: float) -> Optional[float]:
        """掉落物落点：优先取 ref_y 附近的支撑面，否则取下方最近的平台。

        怪悬在空中（飞行怪）或骑在断口时，``_surface_y`` 的近邻搜索会落空；
        旧逻辑此时回退到生成点高度，掉落物便悬在半空。这里补一条「向下找
        最近的 foothold」，让它真正落到下方平台。
        """
        surface = self._surface_y(x, ref_y)
        if surface is not None:
            return surface
        best: Optional[float] = None
        for f in self.assets.footholds:
            x1, x2 = f["x1"], f["x2"]
            if x1 == x2 or not (min(x1, x2) - 1.0 <= x <= max(x1, x2) + 1.0):
                continue
            y = f["y1"] + (f["y2"] - f["y1"]) * (x - x1) / (x2 - x1)
            if y >= ref_y - 2.0 and (best is None or y < best):
                best = y
        return best

    def player_attack(self, player: Combatant,
                      monsters: List[CombatTarget]) -> None:
        """玩家攻击：命中框（或瞬发魔法扇形）内怪物受伤 + 官方命中特效。

        普攻/近战技能：命中框与怪物碰撞盒相交则命中，mobCount 限制最多命中数。
        瞬发魔法（cone_attack）：无弹道。带 WZ lt/rb 的（雷电术）按角色周围矩形
        结算；否则（魔法双击/冰冻术）用与射箭相同的瞄准扇形圈定目标。
        """
        if player.attack_hit_applied:
            return
        rect = player.attack_rect()
        if rect is None:
            return
        player.attack_hit_applied = True
        skill = player.pending_skill
        skill_id = skill["id"] if skill else None
        hit_frames = self.assets.skill_hit_frames(skill_id) if skill_id else []
        cx, cy = player.x, player.y

        attack_count = 1
        if skill:
            mult = skill["damage"]
            attack_count = max(1, int(skill.get("attack_count", 1)))
        else:
            mult = 1.0
        if skill and skill.get("form") == "mob_status":
            self._cast_mob_status(player, skill, monsters)
            return
        if skill and skill.get("cone_attack"):
            targets = self._instant_magic_targets(player, skill, monsters)
        else:
            targets = [m for m in monsters
                       if not m.dead and rect.colliderect(m.rect())]
            if skill:
                targets.sort(key=lambda m: (m.x - cx) ** 2 + (m.cy - cy) ** 2)
                targets = targets[:max(1, skill["mob_count"])]
        magic = bool(skill.get("magic")) if skill else False
        if magic:
            atk_lo, atk_hi = player.magic_attack_range(
                skill.get("skill_mad", 0), skill.get("skill_mastery", 0))
        else:
            atk_lo, atk_hi = player.attack_range()
        player_level = player.level
        crit_rate = player.crit_rate()
        crit_mult = player.crit_mult()

        for mob in targets:
            if self.rng.random() >= stats_mod.hit_chance(
                    player.accuracy_value(), mob.eva,
                    player_level - mob.level):
                self.numbers.append(DamageNumber(
                    mob.x, mob.cy - mob.sprite_h, 0))
                continue
            if hit_frames:
                # 命中特效按 WZ origin 对齐落点：雷电术等竖向特效 origin 在底端，
                # 居中绘制会把落点压到怪物脚下，origin 对齐则从怪物身上向上延伸。
                self.effects.append(Effect(
                    hit_frames, mob.x, mob.cy - mob.sprite_h * 0.45,
                    use_origin=True,
                    flip=getattr(player, "facing_right", True)))
            # 命中附带：魔力吸收回蓝（魔法）、冰冻术冻结
            if magic:
                self._absorb_mp(player, mob)
            if skill and skill.get("freeze", 0) > 0 and hasattr(mob, "apply_freeze"):
                mob.apply_freeze(skill["freeze"])
            self.preferred_mob = mob
            for _ in range(attack_count):
                mob_pd = mob.mdd if magic else mob.pd
                dmg, crit = stats_mod.roll_damage(
                    atk_lo, atk_hi, mult, mob_pd,
                    player_level, mob.level, random,
                    crit_rate, crit_mult)
                self.numbers.append(DamageNumber(
                    mob.x, mob.cy - mob.sprite_h, dmg,
                    "violet" if crit else "red", big=crit))
                died = mob.take_hit(dmg, from_x=player.x)
                if died:
                    self._on_kill(player, mob)
                    break

    def _cast_mob_status(self, player, skill: dict,
                         monsters: List[CombatTarget]) -> None:
        """怪物 debuff（缓速术等）：按 lt/rb 范围（无框则扇形）选最多 mobCount 只，无伤害。

        施放形态由 WZ mob 节点推导；状态种类由 skill["status"]（skill_effects 语义表）给出。
        """
        targets = self._instant_magic_targets(player, skill, monsters)
        if skill.get("status") != "slow":
            return
        mult = max(0.0, 1.0 + skill.get("slow_x", 0) / 100.0)
        for mob in targets:
            if getattr(mob, "dead", False):
                continue
            if hasattr(mob, "apply_slow"):
                mob.apply_slow(mult, skill.get("duration", 0.0))

    def _absorb_mp(self, player: Combatant, mob: CombatTarget) -> None:
        """魔力吸收(2200000)：魔法命中时按技能等级 prop/x 吸怪 MP 回蓝。

        纯被动（不可落键施放），只在玩家已学该技能且怪仍有 MP 时生效；
        概率 prop（%），吸收量 x 不超过怪当前 MP，回蓝不超过自身上限。
        """
        skills = getattr(player, "skills", None)
        if skills is None:
            return
        level = skills.levels.get("2200000", 0)
        d = skills.defs.get("2200000")
        if level <= 0 or d is None:
            return
        mob_mp = getattr(mob, "mp", 0)
        if mob_mp <= 0:
            return
        prop = d.stat(level, "prop", 0)
        amount = min(d.stat(level, "x", 0), mob_mp)
        if prop <= 0 or amount <= 0 or random.random() * 100 >= prop:
            return
        mob.mp = mob_mp - amount
        player.mp = min(player.max_mp, player.mp + amount)

    # ── 远程弹道 ───────────────────────────────────────────────────
    def _in_aim_cone(self, player, facing, mob, ref_y, tan_half, r2):
        """怪是否处于瞄准扇形（半径 × 朝向 ±半顶角）内；是则返回 (点, 距离²)。"""
        if getattr(mob, "dead", False):
            return None
        adx = (mob.x - player.x) * facing        # 朝向前分量
        if adx <= 0:
            return None
        cy = mob.cy - mob.sprite_h / 2.0
        dy = cy - ref_y
        if abs(dy) > adx * tan_half:             # 夹角超出扇形半顶角
            return None
        d2 = adx * adx + dy * dy
        if d2 > r2:
            return None
        return (mob.x, cy), d2

    def _instant_magic_targets(self, player: Combatant, skill: dict,
                               monsters) -> List[CombatTarget]:
        """瞬发魔法命中列表：优先按 WZ lt/rb 矩形，否则按瞄准扇形。

        带 `area`（雷电术等自身 AOE）：以角色 navel 为原点取 lt↔rb 矩形，
        判定怪的中心是否落在框内，不区分朝向、左右皆中。
        无 `area`（魔法双击/冰冻术）：沿用射箭同款瞄准扇形（朝向 ±半顶角、半径）。
        两者都按「集火目标优先、距离次之」排序，取最近 mobCount 只。
        """
        if not monsters:
            return []
        found: List[Tuple[float, CombatTarget]] = []
        ref_y = player.y - 8.0
        area = skill.get("area")
        if area:
            lt, rb = area
            box = pygame.Rect(int(player.x + lt[0]), int(player.y + lt[1]),
                              int(rb[0] - lt[0]), int(rb[1] - lt[1]))
            for mob in monsters:
                if getattr(mob, "dead", False):
                    continue
                cx, cy = mob.x, mob.cy - mob.sprite_h / 2.0
                if not box.collidepoint(int(cx), int(cy)):
                    continue
                found.append(((cx - player.x) ** 2 + (cy - ref_y) ** 2, mob))
        else:
            facing = 1 if getattr(player, "facing_right", True) else -1
            bonus = player.attack_range_bonus() if hasattr(
                player, "attack_range_bonus") else 0.0
            r2 = (settings.ARROW_AIM_RADIUS + bonus) ** 2
            tan_half = math.tan(math.radians(settings.ARROW_AIM_HALF_ANGLE_DEG))
            for mob in monsters:
                hit = self._in_aim_cone(player, facing, mob, ref_y, tan_half, r2)
                if hit is None:
                    continue
                _point, d2 = hit
                found.append((d2, mob))
        preferred = self.preferred_mob
        found.sort(key=lambda t: (t[1] is not preferred, t[0]))
        return [mob for _d2, mob in found[:max(1, int(skill["mob_count"]))]]

    def _aim_point(self, player: Combatant, facing: int,
                   monsters) -> Optional[Tuple[float, float]]:
        """原版式瞄准 + 集火：优先「刚打到的那只」（圈内时），否则扇形内最近。

        防止任务怪在后面、路过残血杂兵被自动瞄走反手拉怪。
        """
        if not monsters:
            return None
        ref_y = player.y - 8.0
        bonus = player.attack_range_bonus() if hasattr(
            player, "attack_range_bonus") else 0.0
        r2 = (settings.ARROW_AIM_RADIUS + bonus) ** 2
        tan_half = math.tan(math.radians(settings.ARROW_AIM_HALF_ANGLE_DEG))
        best: Optional[Tuple[float, float]] = None
        best_d = float("inf")
        preferred = self.preferred_mob
        for mob in monsters:
            hit = self._in_aim_cone(player, facing, mob, ref_y, tan_half, r2)
            if hit is None:
                continue
            point, d2 = hit
            if mob is preferred:                 # 集火目标：一票通过
                return point
            if d2 < best_d:
                best, best_d = point, d2
        return best

    def spawn_arrows(self, player: Combatant, skill_data: Optional[dict],
                     monsters=None) -> None:
        """一次远程起手：按 bulletCount 生成错峰箭，从手部位置出发。

        原版式瞄准：瞄准圈内面朝一侧有怪时，箭沿出手点→怪身体中心方向斜射
        （多发技能所有箭瞄向同一最近目标）；无目标则水平直射。
        skill_data=None 为普攻：单箭、攻击力 100%，
        弹道贴图用箭矢物品的 bullet 节点（原版同款）。
        """
        crit_rate = player.crit_rate()
        crit_mult = player.crit_mult()
        player_level = player.level
        speed, life = settings.ARROW_SPEED, settings.ARROW_LIFETIME
        if skill_data is None:
            mult, attack_count = 1.0, 1
            n, mob_count = 1, 1
            magic = False
            atk_lo, atk_hi = player.attack_range()
            frames = self.assets.normal_arrow_frames() if self.assets else []
            hit_frames: List = []
        else:
            sid = skill_data["id"]
            mult = skill_data["damage"]
            attack_count = max(1, int(skill_data.get("attack_count", 1)))
            magic = bool(skill_data.get("magic"))
            if magic:
                atk_lo, atk_hi = player.magic_attack_range(
                    skill_data.get("skill_mad", 0),
                    skill_data.get("skill_mastery", 0))
            else:
                atk_lo, atk_hi = player.attack_range()
            n = max(1, int(skill_data.get("bullet_count", 1)))
            mob_count = max(1, skill_data["mob_count"])
            frames = self.assets.skill_ball_frames(sid) if self.assets else []
            hit_frames = self.assets.skill_hit_frames(sid) if self.assets else []
            speed = skill_data.get("speed", speed)
            life = skill_data.get("life", life)
        # 被动射程（百步穿楊等）：延长箭矢存活，使其能飞到扩大的瞄准圈
        range_bonus = player.attack_range_bonus() if hasattr(
            player, "attack_range_bonus") else 0.0
        life += range_bonus / speed
        facing = 1 if player.facing_right else -1
        aim = self._aim_point(player, facing, monsters)
        for i in range(n):
            offset = (i - (n - 1) / 2.0) * 7.0     # 多支箭纵向错峰
            ax, ay = player.x + facing * 16.0, player.y - 8.0 + offset
            vx, vy = facing * speed, 0.0
            if aim is not None:
                dx, dy = aim[0] - ax, aim[1] - ay
                dist = math.hypot(dx, dy)
                if dist > 1e-6:
                    vx, vy = dx / dist * speed, dy / dist * speed
            self.arrows.append(Arrow(
                x=ax, y=ay, vx=vx, vy=vy,
                frames=frames, hit_frames=hit_frames,
                dmg=atk_hi, mob_count=mob_count, life=life,
                atk_lo=atk_lo, atk_hi=atk_hi, mult=mult,
                crit_rate=crit_rate, crit_mult=crit_mult,
                player_level=player_level, attack_count=attack_count,
                magic=magic))

    def update_arrows(self, dt: float, monsters, player=None) -> None:
        for a in self.arrows:
            a.update(dt, monsters, self, player)
        self.arrows = [a for a in self.arrows if not a.dead]

    def _on_kill(self, player, mob) -> None:
        """击杀结算：经验 + 掉落（官方 drop_data 优先，缺数据回退启发式）。"""
        self.total_kills += 1
        self.pending_exp.append(mob.exp)
        self.combat_log.add_exp(str(mob.mob_id), getattr(mob, "name", "") or "",
                                mob.exp)
        # 任务进度：击杀计数
        try:
            player.quests.on_kill(int(mob.mob_id))
        except Exception:
            pass
        ground = self._drop_ground(mob.x, mob.cy)
        if self.drop_table is not None and self.drop_table.has_mob(str(mob.mob_id)):
            self._spawn_official_drops(mob, ground, self._active_quest_ids(player))
            return
        meso = mob.exp * random.randint(3, 6) + random.randint(1, 5)
        self.drops.append(DropItem(
            mob.x + random.uniform(-14, 14), mob.cy - 20,
            meso=meso, ground_y=ground, assets=self.assets))
        drop = mob.roll_drop()
        if drop is not None:
            self.drops.append(DropItem(
                mob.x + random.uniform(-18, 18), mob.cy - 20,
                item=drop, ground_y=ground, assets=self.assets))

    @staticmethod
    def _active_quest_ids(player) -> Set[str]:
        """玩家进行中任务 id 集（str）：任务限定掉落的参与判定。"""
        getter = getattr(getattr(player, "quests", None), "active_quests", None)
        return {str(q) for q in getter()} if callable(getter) else set()

    def _spawn_official_drops(self, mob, ground: Optional[float],
                              active_quests: Optional[Set[str]] = None) -> None:
        """官方掉落下同一击杀可出多件物品 + 一堆金币（金币行命中时）。"""
        res = self.drop_table.roll(str(mob.mob_id), active_quests=active_quests)
        if res.meso > 0:
            self.drops.append(DropItem(
                mob.x + random.uniform(-14, 14), mob.cy - 20,
                meso=res.meso, ground_y=ground, assets=self.assets))
        for it in res.items:
            if not self._has_item_icon(it["id"]):
                continue
            name = self.assets.item_name(it["id"]) if self.assets else None
            self.drops.append(DropItem(
                mob.x + random.uniform(-18, 18), mob.cy - 20,
                item={"id": it["id"], "count": it["count"], "name": name},
                ground_y=ground, assets=self.assets))

    def _has_item_icon(self, item_id: str) -> bool:
        """物品图标可解析才生成掉落：解析不出（如 8 位商城道具）宁可不出。"""
        if self.assets is None:
            return True
        found_api = False
        for name in ("item_icon", "equip_icon"):
            getter = getattr(self.assets, name, None)
            if getter is None:
                continue
            found_api = True
            try:
                if getter(item_id) is not None:
                    return True
            except Exception:
                return True
        return True if not found_api else False

    def apply_mob_hits(self, player, hits: List[dict]) -> None:
        """怪物接触伤害队列 → 玩家扣血（无敌帧忽略、回避成功不进入受击态）。

        顺序：接触免疫 → 回避掷骰（MISS 飘蓝字 + 进入接触冷却，但不击退）→
        hurt（硬直+击退+无敌）→ 防御减伤后扣血。命中与 MISS 同受冷却间隔约束。
        防御减伤：伤害 × 100 / (100 + 防御力)，至少保留 1 点。
        附带异常：命中后按各 status_attack 的概率触发毒/晕/减速。
        """
        for hit in hits:
            if player.is_invulnerable():
                continue
            acc = hit.get("acc")
            if acc is not None and self.rng.random() >= stats_mod.hit_chance(
                    acc, player.evasion_value(),
                    hit.get("level", player.level) - player.level):
                player.on_dodge()          # 进入接触冷却，避免连续 MISS 刷屏
                self.numbers.append(DamageNumber(
                    player.x, player.y - 40, 0, "blue"))
                continue
            if not player.hurt(hit["x"]):
                continue
            guard = player.magic_defense_value() if hit.get("magic") \
                else player.defense_value()
            amount = max(1, int(hit["amount"] * 100.0 / (100 + guard)))
            player.take_attack_damage(amount)
            self.numbers.append(DamageNumber(
                player.x, player.y - 40, amount, "red"))
            for atk in hit.get("status_attacks", ()):
                if random.random() * 100.0 < atk.get("prob", 0):
                    player.statuses.apply(atk["kind"], atk["duration"],
                                          atk["potency"])

    def _take(self, drop: "DropItem", player) -> bool:
        """把一件掉落物收进角色：金币入 Combat，物品入背包；放不下则失败。"""
        if drop.is_meso:
            drop.taken = True
            self.meso += drop.meso
            self.combat_log.add_meso(drop.meso)
            return True
        if drop.item is not None:
            item = make_item(drop.item.get("id"), self.assets,
                             count=int(drop.item.get("count") or 1),
                             name=drop.item.get("name"))
            info = drop.item.get("info")
            if isinstance(info, dict):
                # 玩家扔出的装备：恢复其完整属性（已随机的基础 + 强化 + 剩余次数）
                item.info.update({k: int(v) for k, v in info.items()
                                  if isinstance(v, (int, str)) and
                                  str(v).lstrip("-").isdigit()})
                extra = drop.item.get("extra")
                if isinstance(extra, dict):
                    item.extra = {k: int(v) for k, v in extra.items()
                                  if isinstance(v, (int, str)) and
                                  str(v).lstrip("-").isdigit()}
                tuc = drop.item.get("tuc")
                if isinstance(tuc, (int, str)) and str(tuc).lstrip("-").isdigit():
                    item.tuc = int(tuc)
            elif drop.from_mob and item.kind == "equip":
                item.info.update(roll_drop_bonus(self.rng))
            if player.inventory.add(item):
                drop.taken = True
                self.combat_log.add_item(item.id, item.name or "", item.count)
                return True
        return False

    def pickup(self, player) -> bool:
        """按 Z 手动拾取：一次只收取离人物最近的一件掉落物（原版行为）。

        拾取后物品会吸附到角色身上（短暂动画），再收入背包/金币。
        其余掉落物留在原地，再按再捡；背包装备栏满时装备留在地上。
        """
        feet = player.y + settings.FEET_OFFSET
        best = None
        best_dx = float("inf")
        for drop in self.drops:
            if drop.taken or drop._age < drop.pickup_lock or drop.attracting:
                continue
            dx = abs(drop.x - player.x)
            if dx > settings.PICKUP_RANGE or dx >= best_dx:
                continue
            # 同层即可拾取（按落地基准判定，弹跳中/落差略大也不挡）
            if abs(drop.ground_y - feet) > 50.0:
                continue
            best, best_dx = drop, dx
        if best is None:
            return False
        # 启动吸附动画，延迟实际拾取
        best.attracting = True
        best._attract_tx = player.x
        best._attract_ty = player.y - settings.FEET_OFFSET
        best._attract_elapsed = 0.0
        return True

    def drop_player_item(self, player, item) -> DropItem:
        """玩家从背包扔出：从人物中心竖直上抛、自由落体回脚下平台（原版轨迹）。

        带拾取锁避免瞬间捡回；拾取需按 Z 手动触发。
        """
        feet = player.y + settings.FEET_OFFSET
        ground = self._drop_ground(player.x, feet)
        d = DropItem(player.x, player.y,
                     item={"id": item.id, "name": item.name, "count": item.count,
                           "info": dict(item.info), "extra": dict(item.extra),
                           "tuc": item.tuc},
                     ground_y=ground, assets=self.assets,
                     lifetime=settings.DROP_PLAYER_LIFETIME, pickup_lock=0.6,
                     from_mob=False)
        d.vx = 0.0
        d.vy = settings.DROP_THROW_SPEED
        self.drops.append(d)
        return d

    def update(self, dt: float, player=None) -> None:
        """推进战斗实体（伤害飘字 / 特效 / 掉落物物理 / 吸附动画）。"""
        self.numbers = [n for n in self.numbers if n.update(dt)]
        self.combat_log.update()
        for e in self.effects:
            e.update(dt)
        self.effects = [e for e in self.effects if not e.done]
        px = player.x if player is not None else 0.0
        py = player.y if player is not None else 0.0
        for d in self.drops:
            d.update(dt, px, py)
        # 吸附完成的掉落物：实际拾取
        for d in self.drops:
            if not d.attracting or d._attract_elapsed < settings.PICKUP_ATTRACT_TIME:
                continue
            if self._take(d, player):
                d.taken = True
                d.attracting = False
            else:
                d.attracting = False
        self.drops = [d for d in self.drops if d.life > 0 and not d.taken]

    def draw(self, surface: pygame.Surface, camera) -> None:
        for drop in self.drops:
            if not drop.attracting:
                drop.draw(surface, camera)
        for num in self.numbers:
            num.draw(surface, camera, self.assets)

    def draw_attracting(self, surface: pygame.Surface, camera) -> None:
        """绘制正在吸附到角色身上的掉落物（叠在玩家上方）。"""
        for drop in self.drops:
            if drop.attracting:
                drop.draw(surface, camera)

    def draw_arrows(self, surface: pygame.Surface, camera) -> None:
        """飞行中的箭矢（实体之上、特效之下）。"""
        for a in self.arrows:
            a.draw(surface, camera)

    def draw_effects(self, surface: pygame.Surface, camera) -> None:
        """命中火花 / 升级特效（叠在实体之上）。"""
        for e in self.effects:
            e.draw(surface, camera)
