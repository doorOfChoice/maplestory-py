"""交互面板：背包 / 装备栏 / 技能窗口 / 快捷栏。

自绘半透明面板（风格对齐 HUD 的圆角名牌）。窗口打开时由 Game 传入鼠标事件，
点击行为：
  · 背包-消耗页：点击图标使用（喝药）
  · 背包-装备页：点击图标穿戴（同栏位旧装备自动换回）
  · 装备栏：点击已装备栏位脱下
  · 技能窗：点击 [+] 消耗 SP 升级技能
快捷栏常驻 HUD 右下：技能图标 + 键位 + MP 消耗 + 冷却遮罩。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from . import settings
from .inventory import SLOT_ORDER, islot_to_slot

SLOT_NAMES = {
    "cap": "帽子", "face": "脸饰", "earr": "耳环", "top": "上衣",
    "overall": "连身衣", "pants": "裤子", "shoes": "鞋子",
    "glove": "手套", "cape": "披风", "ring": "戒指",
    "shield": "盾牌", "weapon": "武器",
}

CELL = 38          # 物品格 + 间隙
PAD = 10


def _panel(surface: pygame.Surface, rect: pygame.Rect,
           border=(90, 96, 110)) -> None:
    pygame.draw.rect(surface, (18, 22, 30, 216), rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 1, border_radius=8)


def _fit_icon(icon: pygame.Surface, size: int) -> pygame.Surface:
    if icon.get_width() > size or icon.get_height() > size:
        return pygame.transform.scale(icon, (size, size))
    return icon


class Panels:
    def __init__(self, ui, assets):
        self.ui = ui
        self.assets = assets
        self.inv_visible = False
        self.skill_visible = False
        self.inv_tab = "consume"          # consume | equip | etc
        self._tooltip: Optional[str] = None
        self._toast: Optional[Tuple[str, float]] = None   # (文本, 剩余秒)
        self._inv_rect = pygame.Rect(0, 0, 0, 0)
        self._equip_rect = pygame.Rect(0, 0, 0, 0)
        self._skill_rect = pygame.Rect(0, 0, 0, 0)
        self._cell_rects: List[tuple] = []   # (Rect, tab, index)
        self._slot_rects: List[tuple] = []   # (Rect, slot)
        self._skill_rows: List[tuple] = []   # (Rect, skill_id)
        self._tab_rects: List[tuple] = []    # (Rect, tab)

    # ── 开关 ───────────────────────────────────────────────────────
    def toggle_inventory(self) -> None:
        self.inv_visible = not self.inv_visible

    def toggle_skill(self) -> None:
        self.skill_visible = not self.skill_visible

    # ── 图标 ───────────────────────────────────────────────────────
    def _icon(self, item_id: str, kind: str) -> Optional[pygame.Surface]:
        if kind == "equip":
            return self.assets.equip_icon(item_id)
        return self.assets.item_icon(item_id)

    # ── 鼠标点击（返回 True 表示事件已消费）────────────────────────
    def handle_click(self, pos: Tuple[int, int], player) -> bool:
        if self.inv_visible:
            for rect, key in self._tab_rects:
                if rect.collidepoint(pos):
                    self.inv_tab = key
                    return True
            for rect, slot in self._slot_rects:
                if rect.collidepoint(pos):
                    if player.inventory.unequip(slot):
                        player.refresh_equips()
                    else:
                        self.flash("裝備欄已滿")
                    return True
            for rect, tab, idx in self._cell_rects:
                if rect.collidepoint(pos):
                    self._click_cell(player, tab, idx)
                    return True
            if self._inv_rect.collidepoint(pos) or self._equip_rect.collidepoint(pos):
                return True
        if self.skill_visible:
            for rect, sid in self._skill_rows:
                if rect.collidepoint(pos):
                    player.skills.learn_or_upgrade(sid, player.level)
                    return True
            if self._skill_rect.collidepoint(pos):
                return True
        return False

    def _click_cell(self, player, tab: str, idx: int) -> None:
        inv = player.inventory
        if tab == "consume":
            items = list(inv.consumes.values())
            if idx < len(items):
                spec = inv.use_consume(items[idx].id)
                if spec:
                    hp = int(spec.get("hp") or 0)
                    mp = int(spec.get("mp") or 0)
                    if hp:
                        player.hp = min(player.max_hp, player.hp + hp)
                    if mp:
                        player.mp = min(player.max_mp, player.mp + mp)
        elif tab == "equip":
            items = list(inv.equips)
            if idx < len(items) and items[idx].slot is None:
                self.flash(f"無法穿戴 {items[idx].name}")
            elif idx < len(items) and inv.equip(idx):
                player.refresh_equips()
            elif idx < len(items):
                self.flash("裝備欄已滿")

    def flash(self, text: str, duration: float = 1.6) -> None:
        """顶部居中短暂提示（如无法穿戴 / 背包已满）。"""
        self._toast = (text, duration)

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface, player, meso: int = 0) -> None:
        self._tooltip = None
        self._cell_rects.clear()
        self._slot_rects.clear()
        self._skill_rows.clear()
        self._tab_rects.clear()
        mouse = pygame.mouse.get_pos()
        if self.inv_visible:
            self._draw_inventory(surface, player, meso)
            self._draw_equip(surface, player)
        if self.skill_visible:
            self._draw_skills(surface, player)
        if self._tooltip is not None:
            self._draw_tooltip(surface, mouse)
        # 顶部提示
        if self._toast is not None:
            text, remain = self._toast
            remain -= 1 / 60
            if remain <= 0:
                self._toast = None
            else:
                self._toast = (text, remain)
                self._draw_toast(surface, text)

    def _draw_toast(self, surface, text: str) -> None:
        f = self.ui.font
        txt = f.render(text, True, (255, 230, 150))
        w, h = txt.get_width() + 20, 24
        x = (surface.get_width() - w) // 2
        plate = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(plate, (20, 16, 10, 200), (0, 0, w, h), border_radius=6)
        pygame.draw.rect(plate, (150, 130, 90), (0, 0, w, h), 1, border_radius=6)
        plate.blit(txt, (10, (h - txt.get_height()) // 2))
        surface.blit(plate, (x, 34))

    # ── 背包窗口 ───────────────────────────────────────────────────
    def _draw_inventory(self, surface, player, meso: int) -> None:
        inv = player.inventory
        f, fs = self.ui.font, self.ui.font_small
        vh = surface.get_height()

        tab = self.inv_tab
        items = (list(inv.consumes.values()) if tab == "consume"
                 else list(inv.etcs.values()) if tab == "etc"
                 else list(inv.equips))
        cols = 6
        rows = max(2, (max(len(items), 8) + cols - 1) // cols)
        w = PAD * 2 + cols * CELL
        h = 58 + rows * CELL
        x = 12
        y = vh - 150 - h
        rect = pygame.Rect(x, y, w, h)
        self._inv_rect = rect
        _panel(surface, rect)

        # 标题 + 金币
        surface.blit(f.render("道具欄 (I)", True, (235, 235, 240)), (x + PAD, y + 8))
        meso_txt = f.render(f"{meso} 楓幣", True, (255, 220, 90))
        surface.blit(meso_txt, (x + w - PAD - meso_txt.get_width(), y + 8))

        # 页签
        for i, (key, label) in enumerate((("consume", "消耗"), ("equip", "裝備"),
                                          ("etc", "其他"))):
            tr = pygame.Rect(x + PAD + i * 58, y + 28, 54, 18)
            on = key == tab
            pygame.draw.rect(surface, (60, 70, 88) if on else (34, 40, 52),
                             tr, border_radius=4)
            surface.blit(fs.render(label, True, (255, 255, 255)),
                         (tr.x + (tr.w - fs.size(label)[0]) // 2, tr.y + 3))
            self._tab_rects.append((tr, key))

        # 属性摘要（放装备栏窗口，见 _draw_equip）

        # 物品格
        for i in range(cols * rows):
            cx = x + PAD + (i % cols) * CELL
            cy = y + 52 + (i // cols) * CELL
            cell = pygame.Rect(cx, cy, CELL - 4, CELL - 4)
            pygame.draw.rect(surface, (40, 46, 60), cell, border_radius=4)
            if i < len(items):
                item = items[i]
                icon = self._icon(item.id, item.kind)
                if icon is not None:
                    icon = _fit_icon(icon, 32)
                    surface.blit(icon, (cx + (cell.w - icon.get_width()) // 2,
                                        cy + (cell.h - icon.get_height()) // 2))
                if item.count > 1:
                    cnt = fs.render(str(item.count), True, (255, 255, 255))
                    surface.blit(cnt, (cell.right - cnt.get_width() - 2,
                                       cell.bottom - cnt.get_height() + 1))
                if cell.collidepoint(pygame.mouse.get_pos()):
                    self._tooltip = self._item_tip(item)
            self._cell_rects.append((cell, tab, i))

    # ── 装备栏窗口 ─────────────────────────────────────────────────
    def _draw_equip(self, surface, player) -> None:
        inv = player.inventory
        f, fs = self.ui.font, self.ui.font_small
        inv_rect = self._inv_rect
        w = 158
        h = inv_rect.h
        x = inv_rect.right + 10
        y = inv_rect.y
        rect = pygame.Rect(x, y, w, h)
        self._equip_rect = rect
        _panel(surface, rect)
        surface.blit(f.render("裝備欄", True, (235, 235, 240)), (x + PAD, y + 8))
        stat = fs.render(
            f"攻 {player.attack_value()} 防 {player.defense_value()} "
            f"SP {player.skills.sp}", True, (150, 210, 160))
        surface.blit(stat, (x + w - PAD - stat.get_width(), y + 9))

        for i, slot in enumerate(SLOT_ORDER):
            cx = x + PAD + (i % 2) * 70
            cy = y + 32 + (i // 2) * (CELL + 2)
            if cy + CELL > rect.bottom - 6:
                break
            cell = pygame.Rect(cx, cy, 64, CELL - 4)
            pygame.draw.rect(surface, (40, 46, 60), cell, border_radius=4)
            label = fs.render(SLOT_NAMES.get(slot, slot), True, (130, 138, 152))
            surface.blit(label, (cx + 4, cy + 2))
            item = inv.equipped.get(slot)
            if item is not None:
                icon = self._icon(item.id, item.kind)
                if icon is not None:
                    icon = _fit_icon(icon, 22)
                    surface.blit(icon, (cx + cell.w - icon.get_width() - 3,
                                        cy + cell.h - icon.get_height() - 3))
                if cell.collidepoint(pygame.mouse.get_pos()):
                    self._tooltip = self._item_tip(item)
            self._slot_rects.append((cell, slot))

    # ── 技能窗口 ───────────────────────────────────────────────────
    def _draw_skills(self, surface, player) -> None:
        book = player.skills
        f, fs = self.ui.font, self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        sids = sorted(set(book.known()) | set(book.unlocked_for(player.level)),
                      key=lambda s: settings.SKILL_UNLOCK_LEVEL.get(s, 99))
        w = 330
        h = 46 + max(1, len(sids)) * 52 + 8
        x = vw - w - 12
        y = vh - 150 - h
        rect = pygame.Rect(x, y, w, h)
        self._skill_rect = rect
        _panel(surface, rect)
        surface.blit(f.render("技能欄 (K)", True, (235, 235, 240)), (x + PAD, y + 8))
        sp = f.render(f"SP {book.sp}", True,
                      (255, 220, 90) if book.sp > 0 else (140, 146, 160))
        surface.blit(sp, (x + w - PAD - sp.get_width(), y + 8))

        for i, sid in enumerate(sids):
            d = book.defs.get(sid)
            if d is None:
                continue
            lv = book.levels.get(sid, 0)
            ry = y + 40 + i * 52
            row = pygame.Rect(x + PAD, ry, w - PAD * 2, 48)
            pygame.draw.rect(surface, (40, 46, 60), row, border_radius=4)
            icon = self.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (32, 32)),
                             (row.x + 6, ry + 8))
            locked = lv == 0
            color = (140, 146, 160) if locked else (235, 235, 240)
            key = settings.SKILL_HOTKEYS.get(sid)
            keytxt = f"  [{key}]" if key and lv > 0 else ""
            name_txt = f"{d.name} Lv{lv}/{d.max_level}{keytxt}"
            surface.blit(f.render(name_txt, True, color), (row.x + 46, ry + 6))
            desc = d.desc if not locked else f"Lv{settings.SKILL_UNLOCK_LEVEL.get(sid)} 可學習"
            surface.blit(fs.render(desc[:24], True, (150, 156, 170)),
                         (row.x + 46, ry + 26))
            if lv > 0:
                dmg = d.stat(lv, "damage", 100)
                mp = d.stat(lv, "mpCon", 0)
                info = fs.render(f"{dmg}% MP{mp}", True, (150, 210, 160))
                surface.blit(info, (row.right - info.get_width() - 8, ry + 28))
            # 升级按钮
            if book.sp > 0 and lv < d.max_level:
                btn = pygame.Rect(row.right - 26, ry + 4, 22, 22)
                pygame.draw.rect(surface, (70, 130, 90), btn, border_radius=4)
                surface.blit(f.render("+", True, (255, 255, 255)),
                             (btn.x + 7, btn.y + 1))
                self._skill_rows.append((btn, sid))

    # ── 快捷栏（HUD 常驻）──────────────────────────────────────────
    def draw_quickslots(self, surface, player) -> None:
        fs = self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        y = vh - 146
        for sid in settings.SKILL_HOTKEYS:
            d = player.skills.defs.get(sid)
            if d is None or player.skills.levels.get(sid, 0) <= 0:
                continue
            lv = player.skills.levels[sid]
            key = settings.SKILL_HOTKEYS[sid]
            slot = pygame.Rect(0, 0, 46, 46)
            slot.right = vw - 14
            slot.y = y
            _panel(surface, slot, (70, 76, 90))
            icon = self.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (34, 34)),
                             (slot.x + 6, slot.y + 6))
            # 冷却遮罩（自下而上消退）
            cd = player.skills.cooldowns.get(sid, 0.0)
            total = settings.SKILL_COOLDOWN.get(sid, 0.8)
            if cd > 0:
                frac = max(0.0, min(1.0, cd / total))
                cover_h = max(1, int(slot.h * frac))
                shade = pygame.Surface((slot.w, cover_h), pygame.SRCALPHA)
                shade.fill((10, 10, 14, 150))
                surface.blit(shade, (slot.x, slot.y + slot.h - cover_h))
            kb = fs.render(str(key), True, (255, 220, 90))
            surface.blit(kb, (slot.x + 3, slot.y + 2))
            mp = fs.render(f"{d.stat(lv, 'mpCon', 0)}", True, (120, 170, 230))
            surface.blit(mp, (slot.right - mp.get_width() - 3,
                              slot.bottom - mp.get_height() - 2))
            y -= slot.h + 8

    # ── 提示框 ─────────────────────────────────────────────────────
    def _item_tip(self, item) -> str:
        lines = [item.name]
        if item.kind == "equip":
            parts = []
            for key, label in (("incPAD", "攻"), ("incPDD", "防"),
                               ("incSTR", "力"), ("incDEX", "敏"),
                               ("incHP", "HP"), ("incMP", "MP")):
                v = item.stat(key)
                if v:
                    parts.append(f"{label}+{v}")
            if parts:
                lines.append(" ".join(parts))
            slot = islot_to_slot(item.info.get("islot") or "")
            if slot:
                lines.append(SLOT_NAMES.get(slot, slot) + " · 點擊穿上")
            else:
                lines.append("（此 WZ 資源缺少外觀，無法穿戴）")
        elif item.kind == "consume":
            spec = item.info.get("spec") or {}
            if spec.get("hp"):
                lines.append(f"恢復 HP {spec['hp']}")
            if spec.get("mp"):
                lines.append(f"恢復 MP {spec['mp']}")
            lines.append("點擊使用")
        return "\n".join(lines)

    def _draw_tooltip(self, surface, mouse_pos) -> None:
        if self._tooltip is None:
            return
        fs = self.ui.font_small
        f = self.ui.font
        lines = self._tooltip.split("\n")
        w = max(f.size(lines[0])[0],
                max((fs.size(l)[0] for l in lines[1:]), default=0)) + 16
        h = 24 + (len(lines) - 1) * 16 + 6
        x, y = mouse_pos[0] + 14, mouse_pos[1] + 14
        rect = pygame.Rect(x, y, w, h)
        if rect.right > surface.get_width():
            rect.right = surface.get_width()
        if rect.bottom > surface.get_height():
            rect.bottom = surface.get_height()
        _panel(surface, rect, (120, 126, 140))
        surface.blit(f.render(lines[0], True, (245, 220, 140)),
                     (rect.x + 8, rect.y + 4))
        ty = rect.y + 26
        for ln in lines[1:]:
            surface.blit(fs.render(ln, True, (200, 206, 218)), (rect.x + 8, ty))
            ty += 16
