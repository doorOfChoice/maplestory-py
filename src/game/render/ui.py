"""HUD：全部使用 UI.wz 官方素材渲染。

· 底部状态栏：StatusBar/base/backgrnd（浅色长条）+ base/backgrnd2（左侧黑色
  仪表板，自带 "Lv." 凹槽）+ gauge/bar、gauge/gray、gauge/graduation 三段
  （HP / MP / EXP）。HP、MP 数值用 StatusBar/number 像素数字，EXP 用百分比。
  右侧浅色区补上 EquipKey/InvenKey/StatKey 等五个官方 Key 按钮
  （三态 + 按压动画，暂未接功能）。
· NPC 对话 / 系统提示：ChatBalloon/npc 官方黑半透明九宫格气泡（含底部尖尾），
  即原版冒险岛 NPC 谈话窗体；NPC 名为金色首行，正文白色自动换行。
· 死亡界面：红色帷幕 + UIWindow/UtilDlgEx 内嵌白纸窗体（原版系统公告窗）。
· 地图名：半透明黑色圆角名牌（UI.wz 的 MiniMap/title 自带"小地图"字样，
  拉伸会花，故不用）。
中文文本仍用系统 CJK 字体渲染。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.core.fonts import load_cjk_font, render_text
from game.render.conv import (DLG_BOTTOM_H, DLG_LINE_H, DLG_TEXT_BASE, DLG_TEXT_W,
                              DLG_TEXT_X, DLG_TOP_H, DLG_W, ConvPanel,
                              draw_dlg_frame, status_bar_height, ui_image, wrap_text)


def _load_font(size: int) -> pygame.font.Font:
    return load_cjk_font(size)


def compute_bubble_rect(npc_sx: float, npc_top_sy: float, w: int, h: int,
                        tail_w: int, tail_h: int, vw: int, vh: int,
                        gap: int = 6) -> Tuple[int, int, int]:
    """对话气泡定位：水平居中于 NPC 头顶、尖尾指向 NPC，贴边时夹紧到屏内。

    返回 (泡左上角 x, y, 尖尾左上角 x)。世界→屏幕换算由调用方完成后传入。
    """
    x = int(npc_sx - w / 2)
    x = max(4, min(x, vw - w - 4))
    y = max(4, int(npc_top_sy - gap - tail_h - h))
    tail_x = max(x, min(int(npc_sx - tail_w / 2), x + w - tail_w))
    return x, y, tail_x


def fit_bubble_width(content_w: int, vw: int, pad: int = 36,
                     min_w: int = 200, max_w: int = 480) -> int:
    """气泡宽度贴合文本：内容宽 + 内衬，夹在 [min_w, max_w] 且不超屏宽。"""
    return max(min_w, min(max_w, vw - 24, content_w + pad))


# gauge/bar 内三个凹槽的像素范围（x0, x1），填充条在 y=14 起、高 16
SLOT_HP = (2, 107)
SLOT_MP = (110, 215)
SLOT_EXP = (223, 338)
BAR_INNER_Y = 14
BAR_INNER_H = 16

# 状态栏右侧一排官方 Key 按钮（三态 + 按压动画）
KEY_BUTTONS = ("EquipKey", "InvenKey", "StatKey", "SkillKey", "KeySet")
KEY_BTN_GAP = 6          # 按钮间距
KEY_BTN_ANI_MS = 200     # 按压动画两帧总时长

# 点击 Key 按钮 → 切换对应窗口（键为 WindowManager 注册名）
KEY_BUTTON_WINDOWS = {
    "EquipKey": "equip",     # 装备栏
    "InvenKey": "inv",       # 背包
    "StatKey": "stat",       # 属性栏
    "SkillKey": "skill",     # 技能
    "KeySet": "keyconfig",   # 键盘设置
}

# 对话气泡按钮（商店 / 仓库入口）标签
DIALOG_BUTTON_LABELS = {"shop": "购买", "storage": "存取"}


class UI:
    def __init__(self, assets):
        self.assets = assets
        self.font = _load_font(12)
        self.font_big = _load_font(14)
        self.font_small = _load_font(12)
        self.font_tiny = _load_font(12)
        self.dialog_lines: List[str] = []
        self.dialog_visible = False
        self.dialog_anchor = None
        self.death_visible = False
        # 上一帧对话框（气泡）占位矩形，供鼠标点击命中判断
        self.dialog_rect: Optional[pygame.Rect] = None
        # ── 对话框按钮（商店/仓库入口）────────────────────────────
        self._dialog_button_keys: List[str] = []
        self.dialog_buttons: List[Tuple[pygame.Rect, str]] = []
        # ── 状态栏 Key 按钮（热区 / 按下态 / 动画起始 tick）──────────
        self.key_buttons: List[Tuple[pygame.Rect, str]] = []
        self._key_held: Optional[str] = None
        self._key_anim: Optional[Tuple[str, int]] = None
        # ── 会话面板（黑正文行 + 蓝字链接行 + 按钮）：独立组件 ──────
        self.conv = ConvPanel(assets)
        self._plate_cache: dict = {}
        self._balloon_cache: dict = {}

    # ── UI.wz 取图 ──────────────────────────────────────────────────
    def _img(self, img: str, path: str) -> Optional[pygame.Surface]:
        return ui_image(self.assets, img, path)

    # ── 对话框 ─────────────────────────────────────────────────────
    def show_dialog(self, npc_name: str, lines: List[str],
                    anchor=None, buttons: Optional[List[str]] = None) -> None:
        """anchor: 对话中的 NPC 实体（气泡浮其头顶）；None 则屏幕底部居中。

        buttons: 气泡底部的按钮键列表（如 ['shop', 'storage']），供商店/仓库入口。
        """
        self.dialog_lines = [npc_name] + lines
        self.dialog_visible = True
        self.dialog_anchor = anchor
        self._dialog_button_keys = list(buttons or [])
        self.dialog_buttons = []

    def hide_dialog(self) -> None:
        self.dialog_visible = False
        self.dialog_lines = []
        self.dialog_rect = None
        self.dialog_anchor = None
        self._dialog_button_keys = []
        self.dialog_buttons = []

    def dialog_hit(self, pos) -> bool:
        return (self.dialog_visible and self.dialog_rect is not None
                and self.dialog_rect.collidepoint(pos))

    def dialog_button_hit(self, pos) -> Optional[str]:
        """命中对话框按钮 → 返回按钮键（shop/storage），否则 None。"""
        if not self.dialog_visible:
            return None
        for rect, key in self.dialog_buttons:
            if rect.collidepoint(pos):
                return key
        return None

    # ── 状态栏 Key 按钮 ──────────────────────────────────────────────
    def key_button_hit(self, pos) -> Optional[str]:
        """命中 Key 按钮热区 → 返回按钮名，否则 None。"""
        for rect, name in self.key_buttons:
            if rect.collidepoint(pos):
                return name
        return None

    def handle_mouse_event(self, event, pos,
                           now: Optional[int] = None) -> Optional[str]:
        """左键按下命中 Key 按钮 → 启动按压动画并返回按钮名（供 game 层开窗）；
        UP 清按下态返回 None。"""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            name = self.key_button_hit(pos)
            if name is not None:
                self._key_held = name
                self._key_anim = (name, now if now is not None
                                  else pygame.time.get_ticks())
                return name
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._key_held = None
        return None

    def key_button_frame(self, name: str, mouse, left_down: bool,
                         now: int) -> str:
        """按钮当前应显示的贴图路径：动画 > 按下 > 悬停 > 常态。"""
        if self._key_anim is not None and self._key_anim[0] == name:
            elapsed = now - self._key_anim[1]
            if elapsed < KEY_BTN_ANI_MS:
                return f"{name}/ani/{0 if elapsed < KEY_BTN_ANI_MS // 2 else 1}"
            self._key_anim = None
        rect = next((r for r, n in self.key_buttons if n == name), None)
        hovering = rect is not None and rect.collidepoint(mouse)
        if left_down and self._key_held == name and hovering:
            return f"{name}/pressed/0"
        if hovering:
            return f"{name}/mouseOver/0"
        return f"{name}/normal/0"

    def _draw_key_buttons(self, surface, mouse, left_down: bool,
                          bx: int, by: int, bar_w: int, bar_h: int) -> None:
        """状态栏右下一排官方 Key 按钮：按帧状态选贴图并登记热区。"""
        self.key_buttons = []
        now = pygame.time.get_ticks()
        mouse = mouse if mouse is not None else (-1, -1)
        normals = [self._img("StatusBar.img", f"{name}/normal/0")
                   for name in KEY_BUTTONS]
        widths = [n.get_width() if n is not None else 0 for n in normals]
        x = bx + bar_w - 4 - sum(widths) - KEY_BTN_GAP * (len(KEY_BUTTONS) - 1)
        for name, normal in zip(KEY_BUTTONS, normals):
            if normal is None:
                continue
            rect = pygame.Rect(x, by + bar_h - normal.get_height() - 8,
                               normal.get_width(), normal.get_height())
            self.key_buttons.append((rect, name))
            path = self.key_button_frame(name, mouse, left_down, now)
            surf = normal if path == f"{name}/normal/0" else \
                (self._img("StatusBar.img", path) or normal)
            surface.blit(surf, rect.topleft)
            x += rect.width + KEY_BTN_GAP

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
    @staticmethod
    def _wrap(text: str, width: int, font: pygame.font.Font) -> List[str]:
        return wrap_text(text, width, font)

    # ── HUD 绘制 ───────────────────────────────────────────────────
    def draw_hud(self, surface, player, combat, mouse=None,
                 left_down: bool = False) -> None:
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
        exp_txt = render_text(self.font_small, f"{ratios[2] * 100:.2f}%", (255, 255, 255))
        surface.blit(exp_txt, (gx + 250, gy))
        # 等级数字（跟在烤死的 "Lv." 凹槽后面）
        self.draw_wz_number(surface, str(player.level), bx + 36, by + 50)

        # 状态栏右下：一排官方 Key 按钮（三态 + 按压动画）
        self._draw_key_buttons(surface, mouse, left_down, bx, by,
                               bar.get_width(), bar.get_height())

        # 击杀 / 金币 / 背包（白色横栏右端，深色文字）
        info = render_text(
            self.font_small,
            f"击杀 {combat.total_kills}  金币 {combat.meso}  背包 {player.inventory.total_items()}",
            (90, 96, 110))
        surface.blit(info, (bx + bar.get_width() - 240 - info.get_width(), by + 10))

        # 血条上方：生效中的 buff 技能图标 + 状态异常色块（带剩余秒数）
        self._draw_effect_icons(surface, player, bx, by)

        # 地图名：由 game 层按小地图面板位置调用 draw_map_name（右上避让）


    # ── buff / 状态异常图标条（血条上方）──────────────────────────
    def _draw_effect_icons(self, surface, player, bx: int, by: int) -> None:
        """绘制生效中的 buff 技能图标与状态异常色块，右下角标剩余秒数。"""
        buffs = getattr(player, "buffs", None)
        statuses = getattr(player, "statuses", None)
        rows: List[Tuple[object, Optional[pygame.Surface], Tuple[int, int, int]]] = []
        if buffs is not None:
            for b in buffs.active():
                rows.append((b, self.assets.skill_icon(b.skill_id),
                             (120, 200, 255)))
        if statuses is not None:
            colors = {"poison": (120, 230, 120), "stun": (255, 220, 90),
                      "slow": (120, 180, 255)}
            for s in statuses.active():
                rows.append((s, None, colors.get(s.kind, (200, 200, 200))))
        if not rows:
            return
        x = bx
        y = by - 30
        gap = 4
        for obj, icon, color in rows:
            if icon is None:
                icon = pygame.Surface((28, 28), pygame.SRCALPHA)
                pygame.draw.rect(icon, color, (2, 2, 24, 24), border_radius=4)
            surface.blit(icon, (x, y))
            secs = int(obj.remaining)
            label = render_text(self.font_tiny, str(secs), (255, 255, 255))
            surface.blit(label, (x + icon.get_width() - label.get_width(),
                                 y + icon.get_height() - label.get_height()))
            x += icon.get_width() + gap

    def draw_map_name(self, surface, name: str, y: int) -> None:
        """右上角地图名名牌。y 由调用方给出（小地图可见时下移避让）。"""
        hit = self._plate_cache.get(name)
        if hit is None:
            txt = self.font_small.render(name, True, (255, 255, 255))
            w, h = txt.get_width() + 20, 22
            plate = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(plate, (0, 0, 0, 150), (0, 0, w, h), border_radius=6)
            plate.blit(txt, (10, (h - txt.get_height()) // 2))
            hit = plate
            self._plate_cache[name] = hit
        surface.blit(hit, (surface.get_width() - hit.get_width() - 8, y))

    # ── UtilDlgEx 内嵌窗体：转发 render.conv 单源 ──────────────────
    def _dlg_frame(self, surface, x: int, y: int, w: int, content_h: int) -> None:
        draw_dlg_frame(surface, self.assets, x, y, w, content_h)

    def _dlg_layout(self, n_lines: int) -> Tuple[int, int]:
        """返回 (窗体总高, 正文区高)。"""
        content_h = max(60, 40 + n_lines * DLG_LINE_H)
        return DLG_TOP_H + content_h + DLG_BOTTOM_H, content_h

    # ── ChatBalloon/npc 九宫格黑气泡（原版 NPC 谈话窗体）───────────
    def _balloon(self, w: int, h: int) -> Optional[pygame.Surface]:
        key = (w, h)
        hit = self._balloon_cache.get(key)
        if hit is not None:
            return hit
        parts = {}
        for name in ("nw", "n", "ne", "w", "c", "e", "sw", "s", "se"):
            s = self._img("ChatBalloon.img", f"npc/{name}")
            if s is None:
                self._balloon_cache[key] = None
                return None
            parts[name] = s
        cw = parts["nw"].get_width() + parts["ne"].get_width()
        chh = parts["nw"].get_height() + parts["sw"].get_height()
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        inner_w = max(1, w - cw)
        inner_h = max(1, h - chh)
        surf.blit(parts["nw"], (0, 0))
        surf.blit(parts["ne"], (w - parts["ne"].get_width(), 0))
        surf.blit(parts["sw"], (0, h - parts["sw"].get_height()))
        surf.blit(parts["se"], (w - parts["se"].get_width(),
                                h - parts["se"].get_height()))
        surf.blit(pygame.transform.smoothscale(parts["n"], (inner_w, parts["n"].get_height())),
                  (parts["nw"].get_width(), 0))
        surf.blit(pygame.transform.smoothscale(parts["s"], (inner_w, parts["s"].get_height())),
                  (parts["sw"].get_width(), h - parts["s"].get_height()))
        surf.blit(pygame.transform.smoothscale(parts["w"], (parts["w"].get_width(), inner_h)),
                  (0, parts["nw"].get_height()))
        surf.blit(pygame.transform.smoothscale(parts["e"], (parts["e"].get_width(), inner_h)),
                  (w - parts["e"].get_width(), parts["ne"].get_height()))
        surf.blit(pygame.transform.smoothscale(parts["c"], (inner_w, inner_h)),
                  (parts["nw"].get_width(), parts["nw"].get_height()))
        # 原版运行时把白色九宫格乘上 ChatBalloon/npc/clr = 0x80000000（半透黑）
        surf.fill((0, 0, 0, 128), special_flags=pygame.BLEND_RGBA_MULT)
        self._balloon_cache[key] = surf
        return surf

    def _balloon_tail(self) -> Optional[pygame.Surface]:
        hit = self._balloon_cache.get("_tail")
        if hit is not None or "_tail" in self._balloon_cache:
            return hit
        tail = self._img("ChatBalloon.img", "npc/arrow")
        if tail is not None:
            tail = tail.copy()
            tail.fill((0, 0, 0, 128), special_flags=pygame.BLEND_RGBA_MULT)
        self._balloon_cache["_tail"] = tail
        return tail

    def _status_bar_h(self) -> int:
        return status_bar_height(self.assets)

    def status_bar_height(self) -> int:
        """状态栏高度（供聊天框等贴栏而立的 HUD 元件定位）。"""
        return self._status_bar_h()

    # ── 对话框绘制 ─────────────────────────────────────────────────
    def draw_dialog(self, surface, camera=None) -> None:
        if not self.dialog_visible or not self.dialog_lines:
            return
        title, *body = self.dialog_lines
        vw, vh = surface.get_width(), surface.get_height()
        text_w = min(480, vw - 24) - 32
        wrapped: List[str] = []
        for ln in body:
            wrapped.extend(self._wrap(ln, text_w, self.font))
        content_w = max([self.font.size(ln)[0] for ln in wrapped]
                        + [self.font_big.size(title)[0]] or [0])
        bw = fit_bubble_width(content_w, vw)

        keys = getattr(self, "_dialog_button_keys", [])
        self.dialog_buttons = []
        pad_top, line_h, pad_bottom = 12, 19, 14
        strip_h = 26 if keys else 0
        h = pad_top + 21 + len(wrapped) * line_h + pad_bottom + strip_h
        balloon = self._balloon(bw, h)
        tail = self._balloon_tail()
        tail_h = tail.get_height() if tail is not None else 0
        tail_w = tail.get_width() if tail is not None else 0

        anchor = self.dialog_anchor
        if camera is not None and anchor is not None:
            sx, _ = camera.to_screen(anchor.x, anchor.cy)
            _, top_sy = camera.to_screen(anchor.x, anchor.rect().top)
            x, y, tail_x = compute_bubble_rect(
                sx, top_sy, bw, h, tail_w, tail_h, vw, vh)
        else:
            x = (vw - bw) // 2
            y = vh - self._status_bar_h() - tail_h - 4 - h
            tail_x = x + (bw - tail_w) // 2
        self.dialog_rect = pygame.Rect(x, y, bw, h + tail_h)

        if balloon is None:      # 素材缺失退回白纸窗体
            self._draw_dialog_fallback(surface, title, wrapped)
            return
        surface.blit(balloon, (x, y))
        if tail is not None:
            surface.blit(tail, (tail_x, y + h - 1))

        surface.blit(self.font_big.render(title, True, (255, 216, 96)),
                     (x + 16, y + pad_top - 2))
        ty = y + pad_top + 21
        for ln in wrapped:
            shadow = self.font.render(ln, True, (0, 0, 0))
            text = self.font.render(ln, True, (240, 240, 245))
            surface.blit(shadow, (x + 17, ty + 1))
            surface.blit(text, (x + 16, ty))
            ty += line_h

        # 底部按钮（商店 / 仓库入口）
        if keys:
            by = y + pad_top + 21 + len(wrapped) * line_h + 4
            bx = x + bw - 10
            for key in reversed(keys):
                img = self._img("StatusBar.img", "BtShop/normal/0") if key == "shop" else None
                if img is not None:
                    bw_ = img.get_width()
                    bh_ = img.get_height()
                    surface.blit(img, (bx - bw_, by))
                    self.dialog_buttons.append(
                        (pygame.Rect(bx - bw_, by, bw_, bh_), key))
                    bx -= bw_ + 6
                else:
                    label = DIALOG_BUTTON_LABELS.get(key, key)
                    txt = self.font_small.render(label, True, (255, 255, 255))
                    bw_ = txt.get_width() + 16
                    br = pygame.Rect(bx - bw_, by, bw_, 20)
                    pygame.draw.rect(surface, (70, 80, 96), br, border_radius=4)
                    pygame.draw.rect(surface, (150, 160, 178), br, 1, border_radius=4)
                    surface.blit(txt, (br.x + 8, br.y + 3))
                    self.dialog_buttons.append((br, key))
                    bx -= bw_ + 8
        # 原版风格：泡内右下角黄色 ▼ 闪烁指示（无按钮时显示，Enter/Esc/点击关闭）
        elif int(pygame.time.get_ticks() / 500) % 2 == 0:
            bx0, by0 = x + bw - 20, y + h - pad_bottom + 1
            pygame.draw.polygon(surface, (255, 233, 107),
                                [(bx0, by0), (bx0 + 10, by0), (bx0 + 5, by0 + 6)])

    def _draw_dialog_fallback(self, surface, title, wrapped) -> None:
        h, content_h = self._dlg_layout(len(wrapped))
        x = (surface.get_width() - DLG_W) // 2
        y = surface.get_height() - self._status_bar_h() - 8 - h
        self.dialog_rect = pygame.Rect(x, y, DLG_W, h)
        self._dlg_frame(surface, x, y, DLG_W, content_h)
        head = self.font_big.render(title, True, (110, 68, 18))
        surface.blit(head, (x + DLG_TEXT_X, y + 7))
        ty = y + DLG_TOP_H + 8
        for ln in wrapped:
            surface.blit(self.font.render(ln, True, DLG_TEXT_BASE), (x + DLG_TEXT_X, ty))
            ty += DLG_LINE_H
        btn = self._img("UIWindow.img", "UtilDlgEx/BtOK/normal/0")
        if btn is not None:
            bxp = x + DLG_W - btn.get_width() - 12
            byp = y + h - btn.get_height() - 26
            surface.blit(btn, (bxp, byp))

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
        sub = self.font.render("按 R 返回村口重生", True, DLG_TEXT_BASE)
        surface.blit(sub, (x + (374 - sub.get_width()) / 2, y + DLG_TOP_H + 44))
