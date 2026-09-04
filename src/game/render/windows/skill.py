"""技能窗口组件：转数页签 / SP 结余 / 技能列表滚动 / 升级按钮（自 panels.py 迁移）。

保持即时模式：draw() 重建页签与升级按钮热区（_tab_rects / _row_rects），
manager 在事件帧按上一帧登记的 rect 命中回放。滚动状态用 widgets.ScrollList
（step=1，按行滚动），可见行数随页签形态变化（多页签 5 行、否则 6 行）。
坐标遵循 Window 契约：place() 定位限幅，事件 pos 均为 VIEW 坐标。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.core.jobs import job_chain, job_sp_group
from game.render.windows.core import widgets
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DragPickup, Window

# ── 原版窗口几何（由 wz/UI.wz 底图逐像素实测，随 panels 迁移）───────
SKL_BG = "Skill/backgrnd"
SKL_W, SKL_H = 175, 289
SKL_ROW_H = 40           # 技能列表每行高度
SKL_ROWS = 6             # 技能窗一屏可见行数（(SKL_H-49)//SKL_ROW_H）
SKL_ROWS_TAB = 5         # 带转数页签条时的一屏可见行数（页签占 header 下方一条）
SKL_TAB_H = 22           # 转数页签条高度
_SKL_ORD = ("一", "二", "三", "四", "五", "六")   # 转数中文序数
SHT_W = 93               # 快捷栏宽：技能窗锚在其左侧
BAR_RESERVE = 58         # 底部状态栏预留高度
PAD = 10


class SkillWindow(Window):
    """技能窗（K 键）：页签切转、滚轮逐行滚动、点「+」学技能。"""

    key = "skill"

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self._scroll = widgets.ScrollList(step=1)
        self._tab: Optional[int] = None       # 当前 SP 职业组（None=最新一转）
        self._tab_rects: List[Tuple[pygame.Rect, int]] = []
        self._row_rects: List[Tuple[pygame.Rect, str]] = []
        self._drag_rects: List[Tuple[pygame.Rect, str]] = []   # 可上键技能行
        self._visible_rows = SKL_ROWS          # 当前一屏可见行数（绘制时定）

    # ── 定位 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (vw - 4 - SHT_W - 6 - SKL_W, vh - SKL_H - BAR_RESERVE - 2)

    # ── 视图状态 ───────────────────────────────────────────────────
    def _hotkey_of(self, book, sid: str) -> Optional[int]:
        return next((k for k, v in book.hotkeys.items() if v == sid), None)

    def _view(self, book) -> Tuple[List[Tuple[int, str]], int, List[str]]:
        """技能窗当前视图：(页签[(group,label)], 选中 group, 该栏技能 id 列表)。

        页签按职业链旧→新排（一转/二转/三转）；选中栏默认为最新一转，或用户
        点选后记住的 group。列表含该转全部技能（自动满级的被动也列出）。
        """
        tabs, n = [], 0
        for jd in job_chain(book.job):        # 新手页单列名，其余按转数排
            if jd.code == 0:
                tabs.append((job_sp_group(jd.code), "新手"))
            elif n < len(_SKL_ORD):
                tabs.append((job_sp_group(jd.code), _SKL_ORD[n] + "转"))
            n += 1
        groups = [g for g, _ in tabs]
        active = self._tab if self._tab in groups else (
            groups[-1] if groups else job_sp_group(book.job))
        sids = book.skills_for_group(active) if groups else []
        return tabs, active, sids

    def _skill_tip(self, book, d, lv: int, mouse, row: pygame.Rect) -> None:
        """悬停技能行时把描述/伤害/快捷键放进深色 Tooltip，避免行内文字溢出。"""
        if not row.collidepoint(mouse):
            return
        lines = [d.name]
        if d.desc:
            lines.append(d.desc)
        if lv > 0:
            lines.append(f"伤害 {d.stat(lv, 'damage', 100)}% · 消耗 MP{d.stat(lv, 'mpCon', 0)}")
            key = self._hotkey_of(book, d.id)
            if key:
                lines.append(f"快捷键 {key}")
        else:
            need = d.char_level or 1
            lines.append(f"Lv{need} 可学习")
        self.svc.tooltip("\n".join(lines))

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        player = self.svc.player()
        book = player.skills
        tabs, active, sids = self._view(book)
        learn_set = set(book.learnable(active))
        sp_group = book.sp_for_group(active)
        self._tab_rects = []
        self._row_rects = []
        self._drag_rects = []
        if widgets.wz_surface(self.svc, SKL_BG) is None:
            self._draw_fallback(surface, book, tabs, active, sids,
                                learn_set, sp_group)
            return
        self._draw_wz(surface, book, tabs, active, sids, learn_set, sp_group)

    def _draw_wz(self, surface, book, tabs, active, sids,
                 learn_set, sp_group: int) -> None:
        f, ft = self.svc.ui.font, self.svc.ui.font_tiny
        x, y = self.place(surface, (SKL_W, SKL_H))
        surface.blit(widgets.wz_surface(self.svc, SKL_BG), (x, y))
        self.add_chrome(surface, x, y, SKL_W, 44)
        # SP（本转结余，浅色标题条右侧 → 深字）
        sp = ft.render(f"SP {sp_group}", True,
                       (150, 90, 20) if sp_group > 0 else (110, 112, 124))
        surface.blit(sp, (x + 100, y + 7))
        multi = len(tabs) > 1
        if multi:
            self._draw_tabs(surface, x, y + 44, SKL_W, tabs, active)
        list_top = y + (44 + SKL_TAB_H if multi else 49)
        vis_rows = SKL_ROWS_TAB if multi else SKL_ROWS
        self._visible_rows = vis_rows

        sp_btn = widgets.wz_surface(self.svc, "Skill/BtSpUp/normal/0")

        # 技能列表：逐行使用 Skill/skill0(已知)/skill1(未学) 原版行背景，
        # 全宽铺开以盖住 backgrnd 里烤死的深色高亮条，避免文字与底色重叠。
        row_h = SKL_ROW_H
        row_w = SKL_W - 12
        row_x = x + 6
        row_img_h = 38
        mouse = pygame.mouse.get_pos()
        self._scroll.clamp(len(sids), vis_rows)
        start = self._scroll.offset
        for i, sid in enumerate(sids[start:start + vis_rows]):
            d = book.defs.get(sid)
            if d is None:
                continue
            lv = book.levels.get(sid, 0)
            ry = list_top + i * row_h
            locked = lv == 0
            row_img = widgets.wz_surface(
                self.svc, "Skill/skill1" if locked else "Skill/skill0")
            if row_img is not None:
                surface.blit(pygame.transform.scale(row_img, (row_w, row_img_h)),
                             (row_x, ry))
            icon = self.svc.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (28, 28)),
                             (row_x + 3, ry + 3))
            color = (150, 156, 172) if locked else (46, 38, 32)
            tx = row_x + 46
            name_w = row_x + row_w - tx - 8
            name_txt = widgets.ellipsize(f"{d.name} Lv{lv}/{d.max_level}", ft, name_w)
            surface.blit(ft.render(name_txt, True, color), (tx, ry + 5))
            if lv > 0:
                dmg = d.stat(lv, "damage", 100)
                mp = d.stat(lv, "mpCon", 0)
                surface.blit(ft.render(f"{dmg}%  MP{mp}", True, (40, 90, 46)),
                             (tx, ry + 20))
            else:
                surface.blit(ft.render(f"Lv{d.char_level or 1} 可学习", True, color),
                             (tx, ry + 20))
            self._skill_tip(book, d, lv, mouse, pygame.Rect(row_x, ry, row_w, row_img_h))
            if lv > 0 and sid in learn_set:
                self._drag_rects.append(
                    (pygame.Rect(row_x, ry, row_w - 34, row_img_h), sid))
            # 升级按钮（原版 BtSpUp）：仅可手学的主动技能、本转有 SP 且未满级
            if sp_group > 0 and lv < d.max_level and sid in learn_set:
                btn = pygame.Rect(row_x + row_w - 20, ry + 3,
                                  sp_btn.get_width() if sp_btn else 12,
                                  sp_btn.get_height() if sp_btn else 12)
                if sp_btn is not None:
                    surface.blit(sp_btn, btn.topleft)
                else:
                    pygame.draw.rect(surface, (70, 130, 90), btn, border_radius=4)
                    surface.blit(f.render("+", True, (255, 255, 255)),
                                 (btn.x + 3, btn.y))
                self._row_rects.append((btn.inflate(6, 6), sid))

    def _draw_fallback(self, surface, book, tabs, active, sids,
                       learn_set, sp_group: int) -> None:
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        vh = surface.get_height()
        multi = len(tabs) > 1
        tab_band = SKL_TAB_H if multi else 0
        sp_h = 52
        vis_rows = max(1, min(len(sids), (vh - 150 - BAR_RESERVE - tab_band) // sp_h))
        self._visible_rows = vis_rows
        w = 330
        h = 46 + tab_band + vis_rows * sp_h + 8
        x, y = self.place(surface, (w, h))
        widgets.panel_frame(surface, self.rect)
        surface.blit(f.render("技能栏 (K)", True, (235, 235, 240)), (x + PAD, y + 8))
        sp = f.render(f"SP {sp_group}", True,
                      (255, 220, 90) if sp_group > 0 else (140, 146, 160))
        surface.blit(sp, (x + w - PAD - 34 - sp.get_width(), y + 8))
        self.add_chrome(surface, x, y, w, 24)
        if multi:
            self._draw_tabs(surface, x, y + 28, w, tabs, active)
        list_top = y + 40 + tab_band
        mouse = pygame.mouse.get_pos()
        self._scroll.clamp(len(sids), vis_rows)
        start = self._scroll.offset
        for i, sid in enumerate(sids[start:start + vis_rows]):
            d = book.defs.get(sid)
            if d is None:
                continue
            lv = book.levels.get(sid, 0)
            ry = list_top + i * sp_h
            row = pygame.Rect(x + PAD, ry, w - PAD * 2, 48)
            pygame.draw.rect(surface, (40, 46, 60), row, border_radius=4)
            icon = self.svc.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (32, 32)),
                             (row.x + 6, ry + 8))
            locked = lv == 0
            color = (140, 146, 160) if locked else (235, 235, 240)
            key = self._hotkey_of(book, sid)
            keytxt = f"  [{key}]" if key and lv > 0 else ""
            name_txt = widgets.ellipsize(f"{d.name} Lv{lv}/{d.max_level}{keytxt}", f,
                                         row.right - (row.x + 52) - 6)
            surface.blit(f.render(name_txt, True, color), (row.x + 52, ry + 6))
            if lv > 0:
                dmg = d.stat(lv, "damage", 100)
                mp = d.stat(lv, "mpCon", 0)
                info = fs.render(f"{dmg}% MP{mp}", True, (150, 210, 160))
                surface.blit(info, (row.x + 52, ry + 28))
            else:
                surface.blit(fs.render(f"Lv{d.char_level or 1} 可学习",
                                       True, (150, 156, 170)), (row.x + 52, ry + 28))
            self._skill_tip(book, d, lv, mouse, row)
            if lv > 0 and sid in learn_set:
                self._drag_rects.append(
                    (pygame.Rect(row.x, row.y, row.w - 34, row.h), sid))
            if sp_group > 0 and lv < d.max_level and sid in learn_set:
                btn = pygame.Rect(row.right - 26, ry + 4, 22, 22)
                pygame.draw.rect(surface, (70, 130, 90), btn, border_radius=4)
                surface.blit(f.render("+", True, (255, 255, 255)),
                             (btn.x + 7, btn.y + 1))
                self._row_rects.append((btn, sid))

    def _draw_tabs(self, surface, x: int, strip_y: int, w: int,
                   tabs: List[Tuple[int, str]], active: int) -> None:
        """画转数页签条并登记热区；单页（含无页）不画、直接返回。"""
        if len(tabs) <= 1:
            return
        fs = self.svc.ui.font_small
        n = len(tabs)
        tw = max(20, (w - 12) // n)
        for i, (grp, label) in enumerate(tabs):
            r = pygame.Rect(x + 6 + i * tw, strip_y, tw - 2, SKL_TAB_H - 4)
            sel = grp == active
            pygame.draw.rect(surface, (70, 96, 132) if sel else (38, 42, 54),
                             r, border_radius=4)
            if sel:
                pygame.draw.rect(surface, (150, 190, 235), r, 1, border_radius=4)
            t = fs.render(label, True, (245, 245, 250) if sel else (150, 156, 172))
            surface.blit(t, (r.x + (r.w - t.get_width()) // 2,
                             r.y + (r.h - t.get_height()) // 2))
            self._tab_rects.append((r, grp))

    # ── 事件 ───────────────────────────────────────────────────────
    def pickup(self, pos: Tuple[int, int]):
        """按住已学主动技能行 → 起拖一个 skill 载荷（供键盘窗接住）。"""
        for rect, sid in self._drag_rects:
            if rect.collidepoint(pos):
                d = self.svc.player().skills.defs.get(sid)
                return DragPickup(source=("skill", sid), item=None,
                                  home=rect, kind="skill", payload=sid,
                                  label=d.name if d else sid)
        return None

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        for rect, grp in self._tab_rects:
            if rect.collidepoint(pos):
                self._tab = grp
                self._scroll.reset()
                return True
        player = self.svc.player()
        for rect, sid in self._row_rects:
            if rect.collidepoint(pos):
                player.skills.learn(sid, player.level)
                return True
        return self.rect.collidepoint(pos)

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        if not self.rect.collidepoint(pos):
            return False
        book = self.svc.player().skills
        total = len(self._view(book)[2])
        self._scroll.scroll(amount, total, self._visible_rows)
        return True
