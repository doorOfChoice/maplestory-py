"""战斗：攻击判定、伤害飘字、掉落物、经验/升级。

Game 主循环持有 Combat，负责：
  · 玩家攻击命中框 vs 怪物碰撞盒 → 伤害、击退、掉落、经验
  · 怪物接触伤害 → 玩家扣血
  · 伤害飘字动画与绘制
  · 掉落物生成 / 拾取
"""

from __future__ import annotations

import random
from typing import List, Optional

import pygame

from . import settings
from .animation import Animation
from .assets import Assets
from .effects import Effect
from .inventory import make_item


class DamageNumber:
    FONT = None

    def __init__(self, x: float, y: float, amount: int, color=(255, 60, 60)):
        self.x = x
        self.y = y
        self.amount = amount
        self.color = color
        self.life = 0.9
        self.vy = -60.0

    def update(self, dt: float) -> bool:
        self.life -= dt
        self.y += self.vy * dt
        self.vy *= (1 - 2.0 * dt)
        return self.life > 0

    def draw(self, surface: pygame.Surface, camera) -> None:
        if DamageNumber.FONT is None:
            DamageNumber.FONT = pygame.font.Font(None, 20)
        sx, sy = camera.to_screen(self.x, self.y)
        text = DamageNumber.FONT.render(str(self.amount), True, self.color)
        surface.blit(text, (int(sx - text.get_width() / 2), int(sy)))


class DropItem:
    """掉落物：金币（官方硬币旋转动画）或物品（官方 info/icon 图标）。"""

    def __init__(self, x: float, y: float, item: Optional[dict] = None,
                 meso: int = 0, ground_y: Optional[float] = None,
                 assets: Optional[Assets] = None):
        self.x = x
        self.y = y
        self.item = item
        self.meso = int(meso)
        self.assets = assets
        self.life = settings.DROP_LIFETIME
        self.vx = random.uniform(-30, 30)
        self.vy = -120.0
        self.taken = False
        self.name = item.get("name") if item else f"{self.meso} 金幣"
        # 落地基准：脚下 foothold 的表面（略微抬高让图形贴地），缺省用生成点
        self.ground_y = (ground_y if ground_y is not None
                         else y) - 4.0
        self.attracted = False   # 被拾取吸引：自动跳向玩家
        self._age = 0.0

    @property
    def is_meso(self) -> bool:
        return self.item is None

    def update(self, dt: float) -> bool:
        self._age += dt
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
        if self.vy == 0.0 and not self.attracted:
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
            surface.blit(img, (int(sx - img.get_width() / 2),
                               int(sy - img.get_height() / 2)))
            return
        # 图标缺失时的占位（如装备不在本 WZ 子集）
        pygame.draw.circle(surface, (255, 220, 80), (int(sx), int(sy)), 5)
        pygame.draw.circle(surface, (255, 255, 220), (int(sx - 1), int(sy - 1)), 2)


class Combat:
    def __init__(self, assets: Assets):
        self.assets = assets
        self.numbers: List[DamageNumber] = []
        self.drops: List[DropItem] = []
        self.effects: List[object] = []      # 命中火花 / 升级特效等
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

    def player_attack(self, player, monsters) -> None:
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
        hit_frames = self.assets.skill_hit_frames(skill_id or "1001004")
        cx, cy = player.x, player.y

        targets = [m for m in monsters if not m.dead and rect.colliderect(m.rect())]
        if skill:
            max_targets = max(1, skill["mob_count"])
            targets.sort(key=lambda m: (m.x - cx) ** 2 + (m.cy - cy) ** 2)
            targets = targets[:max_targets]
            dmg = int(player.attack_value() * skill["damage"])
        else:
            dmg = player.attack_value()

        for mob in targets:
            self.numbers.append(DamageNumber(
                mob.x, mob.cy - mob.sprite_h, dmg,
                (170, 120, 255) if skill else (255, 60, 60)))
            if hit_frames:
                self.effects.append(Effect(
                    hit_frames, mob.x, mob.cy - mob.sprite_h * 0.45))
            died = mob.take_hit(dmg, from_x=player.x)
            if died:
                self._on_kill(player, mob)

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
        """
        for hit in hits:
            if not player.hurt(hit["x"]):
                continue
            amount = max(1, int(hit["amount"] * 100.0 / (100 + player.defense_value())))
            player.damage(amount)
            self.numbers.append(DamageNumber(
                player.x, player.y - 40, amount, (120, 180, 255)))

    def pickup(self, player) -> bool:
        """玩家拾取掉落 → 金币入 Combat，物品入玩家背包。

        拾起一件后，同层附近的金币/掉落物自动蹦向玩家（原版行为）。
        背包装备栏满时装备留在地上。
        """
        pr = pygame.Rect(int(player.x - 16), int(player.y - 30), 32, 60)
        got = False
        for drop in self.drops:
            if drop.taken:
                continue
            if not pr.colliderect(drop.rect()):
                continue
            if drop.is_meso:
                drop.taken = True
                self.meso += drop.meso
                got = True
            elif drop.item is not None:
                item = make_item(drop.item.get("id"), self.assets,
                                 name=drop.item.get("name"))
                if player.inventory.add(item):
                    drop.taken = True
                    got = True
        if got:
            # 原版行为：拾起一件后，同层附近的金币/掉落物自动蹦向玩家
            feet = player.y + settings.FEET_OFFSET
            for d in self.drops:
                if d.taken or d.attracted:
                    continue
                if abs(d.ground_y - feet) < 50.0 and abs(d.x - player.x) < 300.0:
                    d.attracted = True
        self.drops = [d for d in self.drops if not d.taken]
        return got

    def update(self, dt: float, player=None) -> None:
        self.numbers = [n for n in self.numbers if n.update(dt)]
        for e in self.effects:
            e.update(dt)
        self.effects = [e for e in self.effects if not e.done]
        for d in self.drops:
            if d.attracted and player is not None:
                dx = player.x - d.x
                d.vx = (90.0 if dx >= 0 else -90.0)
                # 落地则再起跳，形成连续蹦跳效果
                if d.vy == 0.0 and d.y >= d.ground_y - 0.5:
                    d.vy = -150.0
            d.update(dt)
        self.drops = [d for d in self.drops if d.life > 0 and not d.taken]

    def draw(self, surface: pygame.Surface, camera) -> None:
        for drop in self.drops:
            drop.draw(surface, camera)
        for num in self.numbers:
            num.draw(surface, camera)

    def draw_effects(self, surface: pygame.Surface, camera) -> None:
        """命中火花 / 升级特效（叠在实体之上）。"""
        for e in self.effects:
            e.draw(surface, camera)
