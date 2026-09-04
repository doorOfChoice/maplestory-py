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
from typing import List, Optional, Protocol, Tuple

import pygame

from game import settings
from game.core import stats as stats_mod
from game.core.animation import Animation
from game.render.assets import Assets
from game.render.effects import Effect
from game.systems.inventory import make_item
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
    def attack_rect(self) -> Optional[pygame.Rect]: ...


class CombatTarget(Protocol):
    """可被攻击的实体（Monster / 合成怪物）所需接口。"""
    x: float
    cy: float
    sprite_h: float
    pd: int
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
                DamageNumber.FONT = pygame.font.Font(None, 20)
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
                surf = surf.copy()
                surf.set_alpha(int(255 * self.alpha))
            surface.blit(surf, (px - origin[0], int(sy) - origin[1]))
            px += surf.get_width()


class DropItem:
    """掉落物：金币（官方硬币旋转动画）或物品（官方 info/icon 图标）。"""

    def __init__(self, x: float, y: float, item: Optional[dict] = None,
                  meso: int = 0, ground_y: Optional[float] = None,
                  assets: Optional[Assets] = None,
                  lifetime: Optional[float] = None, pickup_lock: float = 0.0):
        self.x = x
        self.y = y
        self.item = item
        self.meso = int(meso)
        self.assets = assets
        self.life = settings.DROP_LIFETIME if lifetime is None else lifetime
        self.pickup_lock = pickup_lock   # 生成后短暂不可拾取（玩家扔出防瞬间捡回）
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
            frames = self.assets.meso_frames() if self.assets else []
            if frames:
                idx = Animation.frame_at(frames, self._age * 1000)
                return frames[idx][0]
            return None
        if self.item is not None and self.assets is not None:
            iid = self.item.get("id")
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
                scaled = pygame.transform.smoothscale(img, (sw, sh))
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
                 kind: str = "red", crit: bool = False):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.frames = frames            # [(Surface, origin, delay_ms)]
        self.hit_frames = hit_frames
        self.dmg = dmg
        self.mob_count = max(1, mob_count)
        self.life = life
        self.kind = kind                # 伤害飘字配色（普攻红/技能紫）
        self.crit = crit                # 命中时按暴击大号紫字结算
        self.age = 0.0
        self.hit_ids: set = set()
        self.dead = False
        self._flipped: Optional[list] = None
        self._rot_cache: dict = {}

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 6), int(self.y - 6), 12, 12)

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
            luk = player.luk if player is not None else 0
            dmg = max(1, self.dmg - int(mob.pd * (1 - luk / 100.0)))
            kind = "violet" if (self.crit or self.kind == "violet") else "red"
            combat.numbers.append(DamageNumber(
                mob.x, mob.cy - mob.sprite_h, dmg, kind, big=self.crit))
            if self.hit_frames:
                combat.effects.append(Effect(
                    self.hit_frames, mob.x, mob.cy - mob.sprite_h * 0.45))
            died = mob.take_hit(dmg, from_x=self.x)
            if died and player is not None:
                combat._on_kill(player, mob)
            if len(self.hit_ids) >= self.mob_count:
                self.dead = True
                return
        if self.life <= 0:
            self.dead = True

    def draw(self, surface: pygame.Surface, camera) -> None:
        if not self.frames:
            return
        if abs(self.vy) > 1e-6:
            # 斜射弹道：贴图按速度方向旋转（角度量化缓存）
            idx = Animation.frame_at(self.frames, self.age * 1000.0)
            img, _, _ = self.frames[idx]
            deg = math.degrees(math.atan2(-self.vy, self.vx))
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
        if self.vx < 0:
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
    def __init__(self, assets: Assets):
        self.assets = assets
        self.numbers: List[DamageNumber] = []
        self.drops: List[DropItem] = []
        self.effects: List[object] = []      # 命中火花 / 升级特效等
        self.arrows: List[Arrow] = []        # 飞行中的远程弹道
        self.meso = 0                        # 拾取的金币
        self.total_kills = 0
        self.pending_exp: List[int] = []

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

    def player_attack(self, player: Combatant,
                      monsters: List[CombatTarget]) -> None:
        """玩家攻击：命中框与怪物碰撞盒相交则造成伤害 + 官方命中特效。

        普攻：单目标、攻击力 100%；技能攻击按 level.damage 倍率、
        range 扩大命中框、mobCount 限制最多命中数（取最近的 N 只）。
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

        targets = [m for m in monsters if not m.dead and rect.colliderect(m.rect())]
        if skill:
            max_targets = max(1, skill["mob_count"])
            targets.sort(key=lambda m: (m.x - cx) ** 2 + (m.cy - cy) ** 2)
            targets = targets[:max_targets]
            mult = skill["damage"]
        else:
            mult = 1.0
        atk_lo, atk_hi = player.attack_range()
        player_level = player.level
        crit_rate = player.crit_rate()
        crit_mult = player.crit_mult()

        for mob in targets:
            dmg, crit = stats_mod.roll_damage(
                atk_lo, atk_hi, mult, mob.pd,
                player_level, mob.level, random,
                crit_rate, crit_mult)
            self.numbers.append(DamageNumber(
                mob.x, mob.cy - mob.sprite_h, dmg,
                "violet" if (skill or crit) else "red", big=crit))
            if hit_frames:
                self.effects.append(Effect(
                    hit_frames, mob.x, mob.cy - mob.sprite_h * 0.45))
            died = mob.take_hit(dmg, from_x=player.x)
            if died:
                self._on_kill(player, mob)

    # ── 远程弹道 ───────────────────────────────────────────────────
    def _aim_point(self, player: Combatant, facing: int,
                   monsters) -> Optional[Tuple[float, float]]:
        """原版式瞄准：瞄准扇形（半径 × 朝向 ±半顶角）内最近的怪 → 其身体中心；无则 None（直射）。"""
        if not monsters:
            return None
        ref_y = player.y - 8.0
        best: Optional[Tuple[float, float]] = None
        best_d = float("inf")
        r2 = settings.ARROW_AIM_RADIUS ** 2
        tan_half = math.tan(math.radians(settings.ARROW_AIM_HALF_ANGLE_DEG))
        for mob in monsters:
            if getattr(mob, "dead", False):
                continue
            adx = (mob.x - player.x) * facing        # 朝向前分量
            if adx <= 0:
                continue
            cy = mob.cy - mob.sprite_h / 2.0
            dy = cy - ref_y
            if abs(dy) > adx * tan_half:             # 夹角超出扇形半顶角
                continue
            d2 = adx * adx + dy * dy
            if d2 > r2 or d2 >= best_d:
                continue
            best, best_d = (mob.x, cy), d2
        return best

    def spawn_arrows(self, player: Combatant, skill_data: Optional[dict],
                     monsters=None) -> None:
        """一次远程起手：按 bulletCount 生成错峰箭，从手部位置出发。

        原版式瞄准：瞄准圈内面朝一侧有怪时，箭沿出手点→怪身体中心方向斜射
        （多发技能所有箭瞄向同一最近目标）；无目标则水平直射。
        skill_data=None 为普攻：单箭、攻击力 100%、红色飘字，
        弹道贴图用箭矢物品的 bullet 节点（原版同款）。
        """
        crit_rate = player.crit_rate()
        crit_mult = player.crit_mult()
        player_level = player.level
        atk_lo, atk_hi = player.attack_range()
        speed, life = settings.ARROW_SPEED, settings.ARROW_LIFETIME
        if skill_data is None:
            dmg, crit = stats_mod.roll_damage(
                atk_lo, atk_hi, 1.0, 0, player_level, 0, random,
                crit_rate, crit_mult)
            n, mob_count = 1, 1
            kind = "red"
            frames = self.assets.normal_arrow_frames() if self.assets else []
            hit_frames: List = []
        else:
            sid = skill_data["id"]
            dmg, crit = stats_mod.roll_damage(
                atk_lo, atk_hi, skill_data["damage"], 0, player_level, 0,
                random, crit_rate, crit_mult)
            n = max(1, int(skill_data.get("bullet_count", 1)))
            mob_count = max(1, skill_data["mob_count"])
            kind = "violet"
            frames = self.assets.skill_ball_frames(sid) if self.assets else []
            hit_frames = self.assets.skill_hit_frames(sid) if self.assets else []
            speed = skill_data.get("speed", speed)
            life = skill_data.get("life", life)
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
                dmg=dmg, mob_count=mob_count, kind=kind, crit=crit,
                life=life))

    def update_arrows(self, dt: float, monsters, player=None) -> None:
        for a in self.arrows:
            a.update(dt, monsters, self, player)
        self.arrows = [a for a in self.arrows if not a.dead]

    def _on_kill(self, player, mob) -> None:
        """击杀结算：经验 + 金币必掉 + 概率掉物品。"""
        self.total_kills += 1
        self.pending_exp.append(mob.exp)
        # 任务进度：击杀计数
        try:
            player.quests.on_kill(int(mob.mob_id))
        except Exception:
            pass
        ground = self._surface_y(mob.x, mob.cy)
        meso = mob.exp * random.randint(3, 6) + random.randint(1, 5)
        self.drops.append(DropItem(
            mob.x + random.uniform(-14, 14), mob.cy - 20,
            meso=meso, ground_y=ground, assets=self.assets))
        if random.random() < settings.DROP_ITEM_CHANCE:
            drop = mob.roll_drop()
            if drop is not None:
                self.drops.append(DropItem(
                    mob.x + random.uniform(-18, 18), mob.cy - 20,
                    item=drop, ground_y=ground, assets=self.assets))

    def apply_mob_hits(self, player, hits: List[dict]) -> None:
        """怪物接触伤害队列 → 玩家扣血（受击硬直 + 无敌内忽略）。

        防御减伤：伤害 × 100 / (100 + 防御力)，至少保留 1 点。
        附带异常：命中后按各 status_attack 的概率触发毒/晕/减速。
        """
        for hit in hits:
            if not player.hurt(hit["x"]):
                continue
            amount = max(1, int(hit["amount"] * 100.0 / (100 + player.defense_value())))
            player.damage(amount)
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
            return True
        if drop.item is not None:
            item = make_item(drop.item.get("id"), self.assets,
                             count=int(drop.item.get("count") or 1),
                             name=drop.item.get("name"))
            if player.inventory.add(item):
                drop.taken = True
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
        ground = self._surface_y(player.x, feet)
        d = DropItem(player.x, player.y,
                     item={"id": item.id, "name": item.name, "count": item.count},
                     ground_y=ground, assets=self.assets,
                     lifetime=settings.DROP_PLAYER_LIFETIME, pickup_lock=0.6)
        d.vx = 0.0
        d.vy = settings.DROP_THROW_SPEED
        self.drops.append(d)
        return d

    def update(self, dt: float, player=None) -> None:
        """推进战斗实体（伤害飘字 / 特效 / 掉落物物理 / 吸附动画）。"""
        self.numbers = [n for n in self.numbers if n.update(dt)]
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
