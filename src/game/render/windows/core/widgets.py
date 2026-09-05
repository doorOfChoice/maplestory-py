"""窗口共享小件：WZ 三态按钮 / Tooltip / Toast / 像素数字 / 滚动列表 / 图标适配。

素材路径约定同 panels：UIWindow.img 下 `<prefix>/{normal,mouseOver,pressed}/0`；
任何素材缺失返回 None，由调用方走 fallback 自绘。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.core import item_tip
from game.render.conv import ui_image
from game.render.windows.core.services import WindowServices


# ── 素材与按钮 ─────────────────────────────────────────────────────
def wz_surface(svc: WindowServices, path: str,
               img: str = "UIWindow.img") -> Optional[pygame.Surface]:
    """UIWindow.img 取图：转发 render.conv.ui_image 单源，缺失 None。"""
    return ui_image(svc.assets, img, path)


def ui_button_surface(svc: WindowServices, prefix: str, rect: pygame.Rect,
                      mouse: Tuple[int, int], pressed: bool = False,
                      img: str = "UIWindow.img") -> Optional[pygame.Surface]:
    """WZ 三态按钮图：pressed > mouseOver > normal；素材缺失返回 None。"""
    state = ("pressed" if pressed
             else "mouseOver" if rect.collidepoint(mouse) else "normal")
    return wz_surface(svc, f"{prefix}/{state}/0", img=img)


# ── 自制卷轴图标（234xxxxx 段，Item.wz 无对应素材时自绘）────────────
_scroll_icon: Optional[pygame.Surface] = None


def scroll_icon() -> pygame.Surface:
    """自制强化卷轴的 26×26 自绘卷轴图（模块级缓存，各窗口共用）。"""
    global _scroll_icon
    if _scroll_icon is None:
        surf = pygame.Surface((26, 26), pygame.SRCALPHA)
        pygame.draw.rect(surf, (216, 198, 156), (3, 3, 20, 20), border_radius=2)
        for dx in (7, 12, 17):
            pygame.draw.line(surf, (120, 90, 40), (dx, 5), (dx, 21), 1)
        _scroll_icon = surf
    return _scroll_icon


def fit_icon(icon: pygame.Surface, size: int) -> pygame.Surface:
    """图标等比缩进 size×size 框（不放大）。"""
    if icon.get_width() > size or icon.get_height() > size:
        return pygame.transform.scale(icon, (size, size))
    return icon


def ellipsize(text: str, font: pygame.font.Font, max_w: int) -> str:
    """把文字用省略号截断到 max_w 宽度内，确保不溢出控件边界。"""
    if font.size(text)[0] <= max_w:
        return text
    ell = "..."
    while text and font.size(text + ell)[0] > max_w:
        text = text[:-1]
    return text + ell


# ── 滚动列表状态 ───────────────────────────────────────────────────
class ScrollList:
    """一屏窗口列表的滚动状态：offset 为首条目索引，step 为滚轮一格步进条数。"""

    def __init__(self, step: int = 1) -> None:
        self.offset = 0
        self.step = step

    def clamp(self, total: int, visible: int) -> None:
        self.offset = max(0, min(max(0, total - visible), self.offset))

    def scroll(self, amount: int, total: int, visible: int) -> None:
        self.clamp(total, visible)
        self.offset = max(0, min(max(0, total - visible),
                                 self.offset + amount * self.step))

    def reset(self) -> None:
        self.offset = 0


# ── 官方深色菜单底（ContextMenu t/c/s 三段）────────────────────────
def _stretch_menu_top(t: pygame.Surface, W: int) -> pygame.Surface:
    """顶段横向三段拉伸：左段（箭头+名称条起点）与右边缘保持原宽，
    仅拉伸中段，保证名称条始终左对齐。"""
    tw, th = t.get_size()
    if W == tw:
        return t
    lw, rw = 18, 8
    if W < lw + rw + 1:
        return pygame.transform.smoothscale(t, (W, th))
    out = pygame.Surface((W, th), pygame.SRCALPHA)
    out.blit(t.subsurface(pygame.Rect(0, 0, lw, th)), (0, 0))
    mid = t.subsurface(pygame.Rect(lw, 0, tw - lw - rw, th))
    out.blit(pygame.transform.smoothscale(mid, (W - lw - rw, th)), (lw, 0))
    out.blit(t.subsurface(pygame.Rect(tw - rw, 0, rw, th)), (W - rw, 0))
    return out


def draw_menu_bg(surface, svc: WindowServices, rect: pygame.Rect) -> bool:
    """UIWindow/ContextMenu 三段拼出任意高度深色底；素材缺失返回 False。"""
    t = wz_surface(svc, "ContextMenu/t")
    c = wz_surface(svc, "ContextMenu/c")
    s = wz_surface(svc, "ContextMenu/s")
    if not (t and c and s):
        return False
    W, H = rect.size
    th, sh = t.get_height(), s.get_height()
    top = _stretch_menu_top(t, W)
    bot = s if W == s.get_width() else pygame.transform.smoothscale(s, (W, sh))
    surface.blit(top, rect.topleft)
    surface.blit(bot, (rect.x, rect.bottom - sh))
    mid_h = max(0, H - th - sh)
    if mid_h > 0:
        surface.blit(pygame.transform.smoothscale(c, (W, mid_h)),
                     (rect.x, rect.y + th))
    return True


def panel_frame(surface, rect: pygame.Rect,
                border=(90, 96, 110)) -> None:
    """fallback 自绘面板底（素材缺失时用）。"""
    pygame.draw.rect(surface, (18, 22, 30, 216), rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 1, border_radius=8)


# ── Tooltip / Toast ────────────────────────────────────────────────
TOOLTIP_MAX_W = 320    # Tooltip 最大宽度，超出则正文折行
TOOLTIP_BODY_COLOR = (215, 220, 230)
TOOLTIP_TITLE_COLOR = (245, 220, 140)

# 装备 tooltip 面板配色（参考原版深蓝黑底 + 名称条）
_EQUIP_W = 204
_EQUIP_PAD = 9
_EQUIP_BG = (18, 22, 34)
_EQUIP_BORDER = (92, 104, 132)
_EQUIP_BAND = (44, 62, 104)
_EQUIP_PLATE = (26, 36, 56)
_EQUIP_PLATE_BORDER = (96, 116, 150)
_EQUIP_JOB_PILL = (64, 88, 128)
_EQUIP_NOTE_BG = (30, 40, 60)

_tip_num_font: Optional[pygame.font.Font] = None


def _tip_font_big() -> pygame.font.Font:
    """大数字（攻击力）字号 20 的缓存字体。"""
    global _tip_num_font
    if _tip_num_font is None:
        from game.core.fonts import load_cjk_font
        _tip_num_font = load_cjk_font(20)
    return _tip_num_font


def _tip_lines(tip) -> List[List[item_tip.Seg]]:
    """tooltip 入参归一化：纯文本 → 每行单段（默认正文色）；结构化行原样转列表。"""
    if isinstance(tip, str):
        return [[item_tip.Seg(ln, TOOLTIP_BODY_COLOR)] for ln in tip.split("\n")]
    return [list(ln.segs) for ln in tip]


def _blit_text(surface, font, txt: str, color, x: int, y: int) -> None:
    surface.blit(font.render(txt, True, color), (x, y))


def _draw_equip_tip(surface, svc: WindowServices, mouse_pos: Tuple[int, int],
                    tip: item_tip.EquipTip) -> None:
    """原版装备 tooltip：名称条 + 图标/英雄大数字 + REQ + 职业 + 分类/词条 + 介绍。"""
    fs = svc.ui.font_small
    big = _tip_font_big()
    lh = fs.get_linesize()
    bh = big.get_linesize()
    W, pad = _EQUIP_W, _EQUIP_PAD
    inner = W - pad * 2
    vpad = 8

    # ── 测量各段高度 ────────────────────────────────────────────────
    flag_text = "，".join(tip.flags)
    name_h = lh + 8
    flag_h = lh + 4 if flag_text else 0
    icon_size = 38
    hero_col_h = sum(max(lh, bh) + 3 for _h in tip.heroes) or icon_size
    hero_block_h = max(icon_size + 2, hero_col_h)
    has_req = tip.req_level is not None or bool(tip.req_stats)
    req_h = (lh if tip.req_level is not None else 0) + len(tip.req_stats) * lh
    req_h = req_h + 4 if has_req else 0
    job_h = lh + 6 if tip.jobs else 0
    note_lines = (svc.ui._wrap(tip.note, inner, fs)
                  if tip.note else [])
    note_h = len(note_lines) * lh + 8 if note_lines else 0
    total = (vpad + name_h + flag_h + hero_block_h + req_h + job_h
             + lh + len(tip.stats) * lh + lh + note_h + vpad)

    avail_w = min(W, surface.get_width() - 20)
    x = max(4, min(mouse_pos[0] + 34, surface.get_width() - avail_w - 8))
    y = mouse_pos[1] + 14
    y = min(y, surface.get_height() - total - 8)
    rect = pygame.Rect(x, y, avail_w, total)
    cy = y + vpad

    # ── 底板 + 名称条 ──────────────────────────────────────────────
    panel = pygame.Surface((avail_w, total), pygame.SRCALPHA)
    pygame.draw.rect(panel, (*_EQUIP_BG, 236), (0, 0, avail_w, total),
                     border_radius=8)
    pygame.draw.rect(panel, _EQUIP_BORDER, (0, 0, avail_w, total),
                     1, border_radius=8)
    pygame.draw.rect(panel, _EQUIP_BAND, (0, 0, avail_w, name_h),
                     border_top_left_radius=8, border_top_right_radius=8)
    surface.blit(panel, rect.topleft)

    # 名称（居中于名称条）
    name = ellipsize(tip.name, fs, avail_w - 14)
    _blit_text(surface, fs, name, (240, 244, 252),
               x + (avail_w - fs.size(name)[0]) // 2, cy + 4)
    cy += name_h

    # ── 交换性 / 固有标记 ───────────────────────────────────────────
    if flag_text:
        _blit_text(surface, fs, flag_text, item_tip.GRAY,
                   x + (avail_w - fs.size(flag_text)[0]) // 2, cy)
        cy += flag_h

    # ── 图标 + 攻击力/魔法力大数字 ───────────────────────────────────
    icon = svc.assets.equip_icon(tip.item_id)
    px, py = x + pad + 1, cy + (hero_block_h - icon_size - 2) // 2
    pygame.draw.rect(surface, _EQUIP_PLATE, (px, py, icon_size, icon_size),
                     border_radius=4)
    pygame.draw.rect(surface, _EQUIP_PLATE_BORDER, (px, py, icon_size, icon_size),
                     1, border_radius=4)
    if icon is not None:
        icon = fit_icon(icon, icon_size - 4)
        surface.blit(icon, (px + (icon_size - icon.get_width()) // 2,
                            py + (icon_size - icon.get_height()) // 2))
    hx = px + icon_size + 8
    hy = cy
    for h in tip.heroes:
        _blit_text(surface, fs, h.label, item_tip.GRAY, hx, hy)
        _blit_text(surface, big, _signed_num(h.value), h.color, hx, hy + lh)
        hy += max(lh, bh) + 3
    cy += hero_block_h

    # ── REQ：等级左列，四维右列 ──────────────────────────────────────
    if has_req:
        if tip.req_level is not None:
            label = "REQ LEV  : "
            val = str(tip.req_level)
            _blit_text(surface, fs, label, item_tip.BLUE, x + pad, cy)
            val_color = item_tip.WHITE if tip.req_level_ok else item_tip.RED
            _blit_text(surface, fs, val, val_color,
                       x + pad + fs.size(label)[0], cy)
            cy += lh
        rx = x + pad + (inner // 2) + 4
        for rs in tip.req_stats:
            label = f"REQ {rs.key}  :"
            val = str(rs.need)
            _blit_text(surface, fs, label, item_tip.BLUE, rx, cy)
            val_color = item_tip.WHITE if rs.ok else item_tip.RED
            _blit_text(surface, fs, val, val_color,
                       rx + fs.size(label)[0], cy)
            cy += lh
        cy += 4

    # ── 职业（可穿高亮）──────────────────────────────────────────────
    if tip.jobs:
        job_y = cy
        _blit_jobs(surface, fs, tip.jobs, x + pad, job_y, inner)
        pygame.draw.line(surface, _EQUIP_BORDER, (x + pad, cy + job_h - 6),
                         (x + avail_w - pad, cy + job_h - 6))
        cy += job_h + 2

    # ── 装备分类 + 词条 + 可升级次数（数值右对齐）─────────────────────
    if tip.category:
        _blit_text(surface, fs, f"装备分类  : {tip.category}",
                   item_tip.WHITE, x + pad, cy)
        cy += lh
    for row in tip.stats:
        text_val = _signed_num(row.total, row.tenth)
        _blit_text(surface, fs, row.label, item_tip.WHITE, x + pad, cy)
        _blit_text(surface, fs, text_val, item_tip.STAT_BLUE,
                   x + avail_w - pad - fs.size(text_val)[0], cy)
        if row.extra:
            suffix = _signed_num(row.extra)
            _blit_text(surface, fs, f" ({suffix})", item_tip.GREEN,
                       x + avail_w - pad - fs.size(text_val)[0]
                       + fs.size(text_val)[0], cy)
        cy += lh
    label, val = "可升级次数", str(tip.tuc)
    _blit_text(surface, fs, label, item_tip.WHITE, x + pad, cy)
    _blit_text(surface, fs, val, item_tip.WHITE,
               x + avail_w - pad - fs.size(val)[0], cy)
    cy += lh

    # ── 介绍（String.wz 附注，灰字折行）─────────────────────────────
    if note_lines:
        pygame.draw.rect(surface, _EQUIP_NOTE_BG,
                         (x + pad, cy, avail_w - pad * 2, note_h - 8),
                         border_radius=4)
        ny = cy + 4
        for ln in note_lines:
            _blit_text(surface, fs, ln, item_tip.GRAY, x + pad + 4, ny)
            ny += lh


def _blit_jobs(surface, fs, jobs, x: int, y: int, inner: int) -> int:
    """职业一行：可穿在文字外画圆角胶囊亮底 + 白字，不可穿仅灰字（整行居中）。"""
    gap = 4
    widths = [fs.size(name)[0] for name, _ok in jobs]
    total = sum(widths) + gap * (len(jobs) - 1)
    cx = x + max(0, (inner - total) // 2)
    for name, ok in jobs:
        tw = fs.size(name)[0]
        if ok:
            pygame.draw.rect(surface, _EQUIP_JOB_PILL,
                             (cx - 3, y, tw + 6, 16), border_radius=3)
            _blit_text(surface, fs, name, item_tip.WHITE, cx, y)
        else:
            _blit_text(surface, fs, name, item_tip.GRAY, cx, y)
        cx += tw + gap
    return cx - x


def _signed_num(v: int, tenth: bool = False) -> str:
    """大数字/词条数值文本：tenth 时按 0.1 点换算（15→1.5、10→1）。"""
    if tenth:
        v = v / 10.0
    num = f"{int(v)}" if float(v) == int(v) else f"{v:.1f}"
    return f"+{num}" if v > 0 else num


def draw_tooltip(surface, svc: WindowServices, mouse_pos: Tuple[int, int],
                 tip) -> None:
    """鼠标旁官方深色 Tooltip：首行标题（font），其余按 Seg 分段着色。

    tip 可为纯文本（旧调用方）、core.item_tip.TipLine 结构化行、或装备的
    core.item_tip.EquipTip（走原版双栏面板）；big 段用大字号并撑高行。
    超宽按段折行，单段仍超则按字符拆。
    """
    if isinstance(tip, item_tip.EquipTip):
        _draw_equip_tip(surface, svc, mouse_pos, tip)
        return
    fs, f = svc.ui.font_small, svc.ui.font
    lines = _tip_lines(tip)
    if not lines:
        return
    title = "".join(s.text for s in lines[0])

    def seg_font(seg) -> pygame.font.Font:
        return _tip_font_big() if seg.big else fs

    surfs = [[(seg_font(s).render(s.text, True, s.color), seg_font(s))
              for s in ln] for ln in lines[1:]]
    text_pad = 9
    inner = max([f.size(title)[0]] +
                [sum(surf.get_width() for surf, _ in row) for row in surfs] + [0])
    avail_w = min(inner + text_pad * 2, TOOLTIP_MAX_W, surface.get_width() - 20)
    x = min(mouse_pos[0] + 34, surface.get_width() - avail_w - 20)
    y = mouse_pos[1] + 14
    body_w = avail_w - text_pad * 2

    # 按段折行；单段仍超宽则按字符拆
    rows: List[List[Tuple[pygame.Surface, int]]] = []
    for line, seg_ln in zip(surfs, lines[1:]):
        cur: List[Tuple[pygame.Surface, int]] = []
        cur_w = 0
        for (surf, font), seg in zip(line, seg_ln):
            h = font.get_height()
            if surf.get_width() > body_w:               # 单段超宽（长介绍）
                for chunk in svc.ui._wrap(seg.text, body_w, font):
                    if cur:
                        rows.append(cur)
                        cur, cur_w = [], 0
                    cur.append((font.render(chunk, True, seg.color), h))
                continue
            if cur and cur_w + surf.get_width() > body_w:
                rows.append(cur)
                cur, cur_w = [], 0
            cur.append((surf, h))
            cur_w += surf.get_width()
        rows.append(cur)

    row_h = [max((h for _s, h in r), default=16) for r in rows]
    rect = pygame.Rect(x, y, avail_w, 26 + sum(row_h) + 8)
    if rect.bottom > surface.get_height():
        rect.bottom = surface.get_height()
    if not draw_menu_bg(surface, svc, rect):
        panel_frame(surface, rect, (120, 126, 140))
    surface.blit(f.render(title, True, TOOLTIP_TITLE_COLOR),
                 (rect.x + 14, rect.y + 5))    # 落在左对齐的蓝色名称条内
    ty = rect.y + 27
    for r, rh in zip(rows, row_h):
        tx = rect.x + text_pad
        for surf, h in r:
            surface.blit(surf, (tx, ty + (rh - h) // 2))
            tx += surf.get_width()
        ty += rh


def draw_toast(surface, svc: WindowServices, text: str) -> None:
    """顶部居中短暂提示（如无法穿戴 / 背包已满）。"""
    f = svc.ui.font
    txt = f.render(text, True, (255, 230, 150))
    w, h = txt.get_width() + 20, 24
    x = (surface.get_width() - w) // 2
    plate = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(plate, (20, 16, 10, 200), (0, 0, w, h), border_radius=6)
    pygame.draw.rect(plate, (150, 130, 90), (0, 0, w, h), 1, border_radius=6)
    plate.blit(txt, (10, (h - txt.get_height()) // 2))
    surface.blit(plate, (x, 34))


# ── 原版像素数字（StatusBar/number，白字染色）──────────────────────
class PixelNumbers:
    """数字串的原版像素字体绘制：白 glyph × 染色缓存；不可绘时回退文本。"""

    def __init__(self, svc: WindowServices) -> None:
        self.svc = svc
        self._cache: dict = {}

    def glyph(self, ch: str, color: Tuple[int, int, int]
              ) -> Optional[pygame.Surface]:
        key = (ch, color)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        path = "number/slash" if ch == "/" else f"number/{ch}"
        src = wz_surface(self.svc, path, img="StatusBar.img")
        if src is None:
            return None
        tinted = src.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self._cache[key] = tinted
        return tinted

    def width(self, text: str, color: Tuple[int, int, int]) -> Optional[int]:
        """像素数字串总宽；含不可绘制字符时 None（调用方回退字体）。"""
        w = 0
        for ch in text:
            img = self.glyph(ch, color) if (ch.isdigit() or ch == "/") else None
            if img is None:
                return None
            w += img.get_width() + 1
        return w

    def draw(self, surface, text: str, x: int, y_mid: int,
             color: Tuple[int, int, int] = (60, 60, 60)) -> Optional[int]:
        """绘制一串数字（垂直居中于 y_mid），返回结束 x；不可绘返回 None。"""
        if self.width(text, color) is None:
            return None
        for ch in text:
            img = self.glyph(ch, color)
            surface.blit(img, (x, y_mid - img.get_height() // 2))
            x += img.get_width() + 1
        return x
