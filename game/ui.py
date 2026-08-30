"""HUD：全部使用 UI.wz 官方素材渲染。

· 底部状态栏：StatusBar/base/backgrnd（浅色长条）+ base/backgrnd2（左侧黑色
  仪表板，自带 "Lv." 凹槽）+ gauge/bar、gauge/gray、gauge/graduation 三段
  （HP / MP / EXP）。HP、MP 数值用 StatusBar/number 像素数字，EXP 用百分比。
  右侧浅色区补上 BtShop/BtMenu/BtShort/BtNPT 四个官方菜单按钮。
· NPC 对话 / 系统提示：UIWindow/UtilDlgEx 内嵌白纸窗体（it/ic/is），
  文字只落在白纸区内并自动换行，BtOK 按钮落在底部蓝色页脚。
· 死亡界面：红色帷幕 + 同款窗体。
· 地图名：半透明黑色圆角名牌（UI.wz 的 MiniMap/title 自带"小地圖"字样，
  拉伸会花，故不用）。
中文文本仍用系统 CJK 字体渲染。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from . import settings


def _load_font(size: int) -> pygame.font.Font:
    for name in ("hiraginosansgb", "songti", "arialunicode"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


# gauge/bar 内三个凹槽的像素范围（x0, x1），填充条在 y=14 起、高 16
SLOT_HP = (2, 107)
SLOT_MP = (110, 215)
SLOT_EXP = (223, 338)
BAR_INNER_Y = 14
BAR_INNER_H = 16

# UtilDlgEx 内嵌窗体几何
DLG_W = 529            # it/ic/is 原生宽度
DLG_TOP_H = 28         # it 高
DLG_BOTTOM_H = 58      # is 高（底部蓝色页脚放 BtOK）
DLG_TEXT_X = 16        # 白纸左缘内缩
DLG_TEXT_W = 348       # 白纸内文字换行宽度
DLG_LINE_H = 20

# 状态栏右侧一排官方按钮
BAR_BUTTONS = ("BtShop", "BtMenu", "BtShort", "BtNPT")


class UI:
    def __init__(self, assets):
        self.assets = assets
        self.font = _load_font(13)
        self.font_big = _load_font(16)
        self.font_small = _load_font(12)
        self.dialog_lines: List[str] = []
        self.dialog_visible = False
        self.death_visible = False
        self._plate_cache: dict = {}

    # ── UI.wz 取图 ──────────────────────────────────────────────────
    def _img(self, img: str, path: str) -> Optional[pygame.Surface]:
        hit = self.assets.ui_surface(img, path)
        return hit[0] if hit else None

    # ── 对话框 ─────────────────────────────────────────────────────
    def show_dialog(self, npc_name: str, lines: List[str]) -> None:
        self.dialog_lines = [f"[{npc_name}]"] + lines
        self.dialog_visible = True

    def hide_dialog(self) -> None:
        self.dialog_visible = False
        self.dialog_lines = []

    def show_death(self) -> None:
        self.death_visible = True

    def hide_death(self) -> None:
        self.death_visible = False

    # ── number 像素数字 ────────────────────────────────────────────
    def draw_wz_number(self, surface, text: str, x: int, y: int) -> int:
        """用 StatusBar/number 从 (x,y) 画一串小数字，返回结束 x。"""
        pieces = []
        for ch in text:
            if ch.isdigit():
                s = self._img("StatusBar.img", f"number/{ch}")
            elif ch == "/":
                s = self._img("StatusBar.img", "number/slash")
            else:
                s = None
            if s is None:
                return x
            pieces.append(s)
        for p in pieces:
            surface.blit(p, (x, y))
            x += p.get_width() + 1
        return x

    # ── 文本换行 ───────────────────────────────────────────────────
    def _wrap(self, text: str, width: int, font: pygame.font.Font) -> List[str]:
        lines: List[str] = []
        cur = ""
        for ch in text:
            if cur and font.size(cur + ch)[0] > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines or [""]

    # ── HUD 绘制 ───────────────────────────────────────────────────
    def draw_hud(self, surface, player, combat) -> None:
        vw, vh = surface.get_width(), surface.get_height()
        bar = self._img("StatusBar.img", "base/backgrnd")
        dark = self._img("StatusBar.img", "base/backgrnd2")
        gauge = self._img("StatusBar.img", "gauge/bar")
        gradu = self._img("StatusBar.img", "gauge/graduation")
        gray = self._img("StatusBar.img", "gauge/gray")
        if bar is None or dark is None or gauge is None or gradu is None:
            return
        bx = (vw - bar.get_width()) // 2
        by = vh - bar.get_height()
        surface.blit(bar, (bx, by))
        surface.blit(dark, (bx, by))  # 左侧黑色仪表板（自带 Lv. 凹槽）

        # 三段血量/蓝量/经验：整条 gauge/bar（自带 HP/MP/EXP 标签）打底，
        # 空余部分用 gauge/gray 盖住，最后叠刻度框
        gx, gy = bx + 90, by + 36
        surface.blit(gauge, (gx, gy))
        ratios = (player.hp / max(1, player.max_hp),
                  player.mp / max(1, player.max_mp),
                  player.exp / max(1, player.exp_to_next()))
        if gray is not None:
            empty = pygame.transform.scale(gray, (gray.get_width() * 340, gray.get_height()))
            for (x0, x1), ratio in zip((SLOT_HP, SLOT_MP, SLOT_EXP), ratios):
                fill = int((x1 - x0) * max(0.0, min(1.0, ratio)))
                surface.blit(empty, (gx + x0 + fill, gy + BAR_INNER_Y),
                             pygame.Rect(0, 0, x1 - x0 - fill, gray.get_height()))
        surface.blit(gradu, (gx, gy))

        # 数值：HP/MP 用官方像素数字（跟在烤死的 HP/MP 标签后面）
        self.draw_wz_number(surface, f"{int(player.hp)}/{player.max_hp}", gx + 20, gy + 2)
        self.draw_wz_number(surface, f"{int(player.mp)}/{player.max_mp}", gx + 131, gy + 2)
        exp_txt = self.font_small.render(f"{ratios[2] * 100:.2f}%", True, (255, 255, 255))
        surface.blit(exp_txt, (gx + 250, gy))
        # 等级数字（跟在烤死的 "Lv." 凹槽后面）
        self.draw_wz_number(surface, str(player.level), bx + 36, by + 50)

        # 菜单按钮（浅色区右侧）
        for i, name in enumerate(BAR_BUTTONS):
            btn = self._img("StatusBar.img", f"{name}/normal/0")
            if btn is not None:
                surface.blit(btn, (bx + bar.get_width() - 12 - len(BAR_BUTTONS) * 54
                                   + i * 54, by + bar.get_height() - btn.get_height() - 8))

        # 击杀 / 金币 / 背包（白色横栏右端，深色文字）
        info = self.font_small.render(
            f"擊殺 {combat.total_kills}  金幣 {combat.meso}  背包 {player.inventory.total_items()}",
            True, (90, 96, 110))
        surface.blit(info, (bx + bar.get_width() - 238 - info.get_width(), by + 4))

        # 地图名（右上）
        self._draw_map_name(surface, self.assets.map_name())

        # 操作提示（左上）
        hint = self.font_small.render(
            "I 道具欄  K 技能欄  F 喝藥  1/2 技能  J 攻擊", True, (255, 255, 255))
        plate = pygame.Surface((hint.get_width() + 16, 20), pygame.SRCALPHA)
        pygame.draw.rect(plate, (0, 0, 0, 120), (0, 0, plate.get_width(), 20),
                         border_radius=6)
        plate.blit(hint, (8, 3))
        surface.blit(plate, (8, 8))

    def _draw_map_name(self, surface, name: str) -> None:
        hit = self._plate_cache.get(name)
        if hit is None:
            txt = self.font_small.render(name, True, (255, 255, 255))
            w, h = txt.get_width() + 20, 22
            plate = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(plate, (0, 0, 0, 150), (0, 0, w, h), border_radius=6)
            plate.blit(txt, (10, (h - txt.get_height()) // 2))
            hit = plate
            self._plate_cache[name] = hit
        surface.blit(hit, (surface.get_width() - hit.get_width() - 8, 8))

    # ── UtilDlgEx 内嵌窗体（it/ic/is）──────────────────────────────
    def _dlg_frame(self, surface, x: int, y: int, w: int, content_h: int) -> None:
        """画 UtilDlgEx 窗体：顶 it + 平铺 ic + 底 is。"""
        t = self._img("UIWindow.img", "UtilDlgEx/it")
        c = self._img("UIWindow.img", "UtilDlgEx/ic")
        s = self._img("UIWindow.img", "UtilDlgEx/is")
        if t is None or c is None or s is None:
            return
        if w != t.get_width():
            t = pygame.transform.smoothscale(t, (w, t.get_height()))
            c = pygame.transform.smoothscale(c, (w, c.get_height()))
            s = pygame.transform.smoothscale(s, (w, s.get_height()))
        surface.blit(t, (x, y))
        ny = y + t.get_height()
        remaining = max(0, content_h)
        while remaining > 0:
            hh = min(c.get_height(), remaining)
            surface.blit(c, (x, ny), pygame.Rect(0, 0, w, hh))
            ny += hh
            remaining -= hh
        surface.blit(s, (x, y + t.get_height() + content_h))

    def _dlg_layout(self, n_lines: int) -> Tuple[int, int]:
        """返回 (窗体总高, 正文区高)。"""
        content_h = max(60, 40 + n_lines * DLG_LINE_H)
        return DLG_TOP_H + content_h + DLG_BOTTOM_H, content_h

    # ── 对话框绘制 ─────────────────────────────────────────────────
    def draw_dialog(self, surface) -> None:
        if not self.dialog_visible or not self.dialog_lines:
            return
        title, *body = self.dialog_lines
        wrapped: List[str] = []
        for ln in body:
            wrapped.extend(self._wrap(ln, DLG_TEXT_W, self.font))

        h, content_h = self._dlg_layout(len(wrapped))
        x = (surface.get_width() - DLG_W) // 2
        y = surface.get_height() - 71 - 8 - h
        self._dlg_frame(surface, x, y, DLG_W, content_h)

        # 标题与正文都落在白纸区内
        head = self.font_big.render(title, True, (110, 68, 18))
        surface.blit(head, (x + DLG_TEXT_X, y + 7))
        ty = y + DLG_TOP_H + 8
        for ln in wrapped:
            surface.blit(self.font.render(ln, True, (60, 52, 44)), (x + DLG_TEXT_X, ty))
            ty += DLG_LINE_H

        # 确认按钮（底部蓝色页脚内，靠右）
        btn = self._img("UIWindow.img", "UtilDlgEx/BtOK/normal/0")
        if btn is not None:
            bxp = x + DLG_W - btn.get_width() - 12
            byp = y + h - btn.get_height() - 26
            surface.blit(btn, (bxp, byp))
            tip = self.font_small.render("確認", True, (60, 52, 44))
            surface.blit(tip, (bxp + (btn.get_width() - tip.get_width()) // 2,
                               byp + (btn.get_height() - tip.get_height()) // 2))

    # ── 死亡提示 ───────────────────────────────────────────────────
    def draw_death(self, surface) -> None:
        if not self.death_visible:
            return
        veil = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
        veil.fill((40, 0, 0, 160))
        surface.blit(veil, (0, 0))

        h, content_h = self._dlg_layout(2)
        x = (surface.get_width() - DLG_W) // 2
        y = (surface.get_height() - h) // 2 - 30
        self._dlg_frame(surface, x, y, DLG_W, content_h)

        txt = self.font_big.render("你 已 死 亡", True, (185, 45, 45))
        surface.blit(txt, (x + (374 - txt.get_width()) / 2, y + DLG_TOP_H + 14))
        sub = self.font.render("按 R 返回村口重生", True, (60, 52, 44))
        surface.blit(sub, (x + (374 - sub.get_width()) / 2, y + DLG_TOP_H + 44))
