"""状态窗（B 键）：UIWindow/Stat 底板 + BtApUp 加点 + BtAuto 一键分配 +
BtDetail「詳細說明」详情弹窗。

即时模式：加点热区（_ap_rects / _auto_rect / _detail_rect）在 draw() 中重建，
manager 下一帧命中回放。像素数字走 widgets.PixelNumbers（StatusBar/number），
素材缺失整体回退旧自绘面板（210×250，锚点同旧 panels._draw_stat_fallback）。
「詳細說明」弹窗用官方 Stat/backgrnd2（184×203）烘焙的九行战斗数值标签，
现只填 攻擊力/物理防禦力 两行（其余留白待补）。
坐标约定：事件 pos 为内部视口（VIEW）坐标。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pygame

from game.core.jobs import JOBS
from game.core.stats import STAT_LABELS
from game.render.windows.core import widgets
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import Window

# ── 原版窗口几何（由 panels.py 迁移，wz/UI.wz 底图逐像素实测）──────
STAT_BG = "Stat/backgrnd"
STAT_W, STAT_H = 175, 337
STAT_TEXT_X = 60                     # 数值文字左缘
STAT_ROW_Y = {"name": 33, "job": 52, "level": 69, "guild": 87,
              "hp": 105, "mp": 123, "exp": 141, "honor": 163}
STAT_AP_BOX = (63, 206, 25, 13)      # 「升级点数」白框
STAT_ROW: Dict[str, int] = {"str": 235, "dex": 253, "int": 271, "luk": 289}
STAT_BT_X = 158                      # BtApUp x
STAT_AUTO_POS = (96, 195)            # BtAuto（73×35）升级点数(63,206)右侧、垂直居中共对齐
STAT_DETAIL_POS = (102, 313)         # BtDetail（63×19）右下、贴近窗口底

# 「詳細說明」详情弹窗（官方 Stat/backgrnd2，184×203，九行标签 y 实测）
STAT_DETAIL_BG = "Stat/backgrnd2"
DETAIL_W, DETAIL_H = 184, 203
DETAIL_ROW_Y = {"atk": 15, "pdd": 33, "mad": 51, "mdd": 69,
                "acc": 87, "eva": 105, "spd": 123, "move": 141, "jump": 160}
DETAIL_VALUE_X = 176                 # 数值右缘（右对齐）

FB_W, FB_H = 210, 250                # 素材缺失时的自绘窗尺寸
NO_AP_TEXT = "没有可分配的属性点"


class StatWindow(Window):
    """状态窗：展示职业/等级/HP/MP/经验/AP/四维，嵌加点按钮。"""

    key = "stat"

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self.numbers = widgets.PixelNumbers(svc)
        self._ap_rects: List[Tuple[pygame.Rect, str]] = []
        self._auto_rect: Optional[pygame.Rect] = None
        self._detail = False                          # 「詳細說明」弹窗开关
        self._detail_rect: Optional[pygame.Rect] = None
        self._detail_popup_rect: Optional[pygame.Rect] = None
        self._fallback = False

    # ── 定位 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        if self._detail:          # 详情贴右缘，主窗整体左移一档
            if self._fallback:
                return (vw - FB_W - DETAIL_W - 8, 60)
            return (vw - STAT_W - DETAIL_W - 8, 140)
        if self._fallback:
            return (vw - FB_W - 8, 60)
        return (vw - STAT_W - 4, 140)

    # ── 事件 ───────────────────────────────────────────────────────
    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        player = self.svc.player()
        if self._detail_rect is not None and self._detail_rect.collidepoint(pos):
            self._detail = not self._detail
            return True
        if self._detail_popup_rect is not None \
                and self._detail_popup_rect.collidepoint(pos):
            return True                       # 弹窗区域消费点击，不穿透世界
        for rect, st in self._ap_rects:
            if rect.collidepoint(pos):
                if not player.allocate_ap(st):
                    self.svc.flash(NO_AP_TEXT)
                return True
        if self._auto_rect is not None and self._auto_rect.collidepoint(pos):
            if not player.auto_allocate_ap():
                self.svc.flash(NO_AP_TEXT)
            return True
        return self.rect.collidepoint(pos)

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        self._ap_rects.clear()
        self._auto_rect = None
        self._detail_rect = None
        player = self.svc.player()
        fs = self.svc.ui.font_small
        bg = widgets.wz_surface(self.svc, STAT_BG)
        self._fallback = bg is None
        if bg is None:
            self._draw_fallback(surface, player, fs)
            return
        x, y = self.place(surface, (STAT_W, STAT_H))
        surface.blit(bg, (x, y))
        self.add_chrome(surface, x, y, STAT_W, 20)
        mouse = pygame.mouse.get_pos()
        total = player.total_stats()
        jobdef = JOBS.get(player.job) or JOBS[0]

        def row(key: str, text: str) -> None:
            surface.blit(fs.render(text, True, (40, 40, 40)),
                         (x + STAT_TEXT_X, y + STAT_ROW_Y[key] + 2))

        def num(key: str, text: str) -> None:
            band = y + STAT_ROW_Y[key]
            if self.numbers.draw(surface, text, x + STAT_TEXT_X, band + 7) is None:
                surface.blit(fs.render(text, True, (40, 40, 40)),
                             (x + STAT_TEXT_X, band + 2))

        row("name", "玩家")
        row("job", jobdef.name)
        num("level", str(player.level))
        num("hp", f"{int(player.hp)}/{player.max_hp}")
        num("mp", f"{int(player.mp)}/{player.max_mp}")
        num("exp", f"{player.exp}/{player.exp_to_next()}")
        bx, by, bw, bh = STAT_AP_BOX
        ap_txt = str(player.ap)
        ap_w = self.numbers.width(ap_txt, (60, 60, 60))
        if ap_w is not None:
            self.numbers.draw(surface, ap_txt, x + bx + (bw - ap_w) // 2,
                              y + by + bh // 2)
        else:
            t = fs.render(ap_txt, True, (40, 40, 40))
            surface.blit(t, (x + bx + (bw - t.get_width()) // 2,
                             y + by + (bh - t.get_height()) // 2))
        for st, ry in STAT_ROW.items():
            bonus = player.inventory.bonus(st)
            text = str(total[st])
            end = self.numbers.draw(surface, text, x + STAT_TEXT_X, y + ry + 7)
            if end is None:
                surface.blit(fs.render(text, True, (40, 40, 40)),
                             (x + STAT_TEXT_X, y + ry + 2))
                end = x + STAT_TEXT_X + fs.size(text)[0]
            if bonus:
                surface.blit(fs.render(f" (+{bonus})", True, (46, 120, 40)),
                             (end + 2, y + ry + 2))
            rect = pygame.Rect(x + STAT_BT_X, y + ry, 12, 12)
            self._ap_rects.append((rect, st))
            if player.ap <= 0:
                img = widgets.wz_surface(self.svc, "Stat/BtApUp/disabled/0")
            else:
                img = widgets.ui_button_surface(self.svc, "Stat/BtApUp",
                                                rect, mouse)
            if img is not None:
                surface.blit(img, rect.topleft)
        rect = pygame.Rect(x + STAT_AUTO_POS[0], y + STAT_AUTO_POS[1], 73, 35)
        self._auto_rect = rect
        img = widgets.ui_button_surface(self.svc, "Stat/BtAuto", rect, mouse)
        if img is not None:
            surface.blit(img, rect.topleft)
        dbtn = pygame.Rect(x + STAT_DETAIL_POS[0], y + STAT_DETAIL_POS[1], 63, 19)
        self._detail_rect = dbtn
        img = widgets.ui_button_surface(self.svc, "Stat/BtDetail", dbtn, mouse)
        if img is not None:
            surface.blit(img, dbtn.topleft)
        self._draw_detail(surface, player, fs)
        self._swallow_detail(surface)

    def _draw_detail(self, surface, player, fs) -> None:
        """「詳細說明」弹窗：官方 Stat/backgrnd2 底图，填 攻擊力/物理防禦力。"""
        self._detail_popup_rect = None
        if not self._detail:
            return
        vw = surface.get_width()
        dx = min(self.rect.right + 4, vw - DETAIL_W - 4)   # 贴主窗右侧，限幅不越屏
        dy = max(0, self.rect.y + 10)
        self._detail_popup_rect = pygame.Rect(dx, dy, DETAIL_W, DETAIL_H)
        bg = widgets.wz_surface(self.svc, STAT_DETAIL_BG)
        if bg is None:
            self._draw_detail_fallback(surface, player, fs, dx, dy)
            return
        surface.blit(bg, (dx, dy))
        for key, val in (("atk", player.attack_value()),
                         ("pdd", player.defense_value())):
            self._draw_detail_value(surface, fs, dx, dy, DETAIL_ROW_Y[key], val)

    def _draw_detail_value(self, surface, fs, dx: int, dy: int,
                           ry: int, val: int) -> None:
        """详情弹窗单行数值（右对齐、垂直居中于标签行）。"""
        text = str(val)
        right = dx + DETAIL_VALUE_X
        w = self.numbers.width(text, (40, 40, 40))
        if w is not None:
            self.numbers.draw(surface, text, right - w, dy + ry)
        else:
            t = fs.render(text, True, (40, 40, 40))
            surface.blit(t, (right - t.get_width(), dy + ry - t.get_height() // 2))

    def _swallow_detail(self, _surface) -> None:
        """详情弹窗打开时把本窗命中矩形并到弹窗，使 manager 能路由弹窗点击。"""
        if self._detail and self._detail_popup_rect is not None:
            self.rect = self.rect.union(self._detail_popup_rect)

    def _draw_detail_fallback(self, surface, player, fs, dx: int, dy: int) -> None:
        """素材缺失时的自绘详情弹窗（只列已实现的攻击/防御两行）。"""
        widgets.panel_frame(surface, pygame.Rect(dx, dy, DETAIL_W, DETAIL_H))
        ty = dy + 18
        for ln in (f"攻击力  {player.attack_value()}",
                   f"物理防御力  {player.defense_value()}"):
            surface.blit(fs.render(ln, True, (230, 225, 210)), (dx + 12, ty))
            ty += 24

    def _draw_fallback(self, surface, player, fs) -> None:
        """素材缺失时的自绘状态窗（含加点按钮热区）。"""
        x, y = self.place(surface, (FB_W, FB_H))
        rect = pygame.Rect(x, y, FB_W, FB_H)
        widgets.panel_frame(surface, rect)
        self.add_chrome(surface, x, y, FB_W, 24)
        total = player.total_stats()
        jobdef = JOBS.get(player.job) or JOBS[0]
        lines = [f"职业：{jobdef.name}    等级：{player.level}",
                 f"HP {int(player.hp)}/{player.max_hp}   "
                 f"MP {int(player.mp)}/{player.max_mp}",
                 f"经验 {player.exp}/{player.exp_to_next()}",
                 f"属性点：{player.ap}"]
        ty = y + 30
        for line in lines:
            surface.blit(fs.render(line, True, (230, 225, 210)), (x + 10, ty))
            ty += 20
        for st in STAT_ROW:
            bonus = player.inventory.bonus(st)
            txt = f"{STAT_LABELS[st]} {total[st]}" + (f" (+{bonus})" if bonus else "")
            surface.blit(fs.render(txt, True, (230, 225, 210)), (x + 10, ty))
            btn = pygame.Rect(x + FB_W - 26, ty - 2, 16, 16)
            self._ap_rects.append((btn, st))
            color = (90, 96, 110) if player.ap <= 0 else (150, 190, 150)
            pygame.draw.rect(surface, color, btn, border_radius=3)
            pygame.draw.line(surface, (250, 250, 250),
                             (btn.x + 8, btn.y + 3), (btn.x + 8, btn.y + 13), 2)
            pygame.draw.line(surface, (250, 250, 250),
                             (btn.x + 3, btn.y + 8), (btn.x + 13, btn.y + 8), 2)
            ty += 24
        abtn = pygame.Rect(x + 100, y + 88, 56, 20)   # 属性点行右侧
        self._auto_rect = abtn
        pygame.draw.rect(surface, (110, 130, 160), abtn, border_radius=4)
        at = fs.render("自动", True, (240, 240, 240))
        surface.blit(at, (abtn.x + (abtn.w - at.get_width()) // 2,
                          abtn.y + (abtn.h - at.get_height()) // 2))
        dbtn = pygame.Rect(x + FB_W - 70, y + FB_H - 30, 64, 22)
        self._detail_rect = dbtn
        pygame.draw.rect(surface, (110, 130, 160), dbtn, border_radius=4)
        dt = fs.render("详细说明", True, (240, 240, 240))
        surface.blit(dt, (dbtn.x + (dbtn.w - dt.get_width()) // 2,
                          dbtn.y + (dbtn.h - dt.get_height()) // 2))
        self._draw_detail(surface, player, fs)
        self._swallow_detail(surface)
