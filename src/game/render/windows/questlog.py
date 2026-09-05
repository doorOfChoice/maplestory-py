"""任务日志窗（Q 键）：官方双联排 —— 左列表窗(backgrnd) + 右详情窗(backgrnd2)。

列表窗顶部三页签（可以开始/正在进行/完成，Quest/Tab_{enabled|disabled}_i），
下方可滚动任务行，点行选中并驱动详情窗；详情窗蓝色头部左侧白字显示任务名 /
等级 / 职业 / 连续任务与进度条（Quest/Gauge*），右侧画目标 NPC 站立立绘，
白色区域展示任务说明与目标行（或点「任务资讯」切到奖励视图），
右下角 BtDetail / BtGiveup。放弃走 QuestLog.abandon。
素材缺失回退自绘 panel_frame；底部为状态栏预留 BAR_RESERVE 高度。
坐标约定：事件 pos 为内部视口（VIEW）坐标。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import pygame

from game.core.jobs import JOBS
from game.render.windows.core import widgets
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import Window
from game.systems.quests import render_markup, split_item_icons

# ── 原版窗口几何（UI.wz/UIWindow.img/Quest 实测）────────────────────
LIST_W, LIST_H = 245, 396      # backgrnd：标题 y1~11 / 页签带 y13~44 / 列表 y45~364
DET_W, DET_H = 305, 396        # backgrnd2：蓝头 y28~118（分隔线 x190）/ 内容 y120~365
GAP = 6
QUEST_WIN_W = LIST_W + GAP + DET_W
ROW_H = 16
LIST_TOP, LIST_BOT = 46, 364
VISIBLE_ROWS = (LIST_BOT - LIST_TOP) // ROW_H
BAR_RESERVE = 58               # 底部状态栏预留高度
BTN_W, BTN_H = 57, 17          # BtDetail / BtGiveup
BODY_TOP, BODY_BOT = 126, DET_H - 34   # 详情白色内容区（滚动视口）上下缘
HEADER_BLUE = (68, 136, 187)   # backgrnd2 蓝头底色（fallback 与选中行同色）

# 官方 desc 里的静态目标行：以 #t/#c/#o 等实体宏开头、以 /N 结尾（如 "#t4000011# …/10"）
_STATIC_GOAL_RE = re.compile(r"^#\w\d+#.*?/\d+\s*$")


def strip_static_goal_lines(desc: str) -> str:
    """剔除 desc 中的官方静态目标行（原始客户端只有文字描述、无进度可显示）。

    进行中页会另挂动态进度行（收集 … 0/N），两者并存会重复展示同一目标；
    仅整行为「实体宏 … /N」才剔除，正文中间引用宏的句子不受影响。
    """
    out = desc.replace("\\r\\n", "\n").replace("\\n", "\n")
    kept = [ln for ln in out.split("\n") if not _STATIC_GOAL_RE.match(ln.strip())]
    return "\n".join(kept)


TAB_KEYS = ("ready", "active", "done")
# 官方页签文字烤死在底图内（可執行/進行中/完成），此表仅素材缺失 fallback 用
TAB_LABEL = {"ready": "可执行", "active": "进行中", "done": "完成"}
TAB_INDEX = {"ready": 0, "active": 1, "done": 2}
DEFAULT_TAB = "active"


class QuestLogWindow(Window):
    """任务日志：页签过滤 + 行选中 + 详情（说明/奖励）+ 放弃。"""

    key = "questlog"

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self.tab: str = DEFAULT_TAB
        self.selected: Optional[str] = None
        self.show_reward: bool = False
        self.list_offset: int = 0
        self.detail_offset: int = 0
        self.tab_rects: Dict[str, pygame.Rect] = {}
        self.row_rects: List[Tuple[pygame.Rect, str]] = []
        self.info_rect: Optional[pygame.Rect] = None
        self.giveup_rect: Optional[pygame.Rect] = None

    # ── 数据 ───────────────────────────────────────────────────────
    def quests_for_tab(self, tab: str) -> List[str]:
        """当前页签对应的 qid 列表（可接按 can_start、完成按 is_completed）。

        可接页排序：有等级限制的排前并按 lvmin 从高到低，无限制的靠后。
        """
        player = self.svc.player()
        quests = player.quests
        defs = quests.defs
        if tab == "active":
            return [qid for qid in quests.accepted_order
                    if quests.is_accepted(qid) and qid in defs]
        if tab == "done":
            return sorted((qid for qid in defs if quests.is_completed(qid)),
                          key=lambda q: (len(q), q))
        return sorted((qid for qid in defs if quests.can_start(qid, player)),
                      key=lambda q: (defs[q].lvmin == 0, -defs[q].lvmin,
                                     len(q), q))

    def _ensure_selection(self, ids: List[str]) -> None:
        if self.selected not in ids:
            self.selected = ids[0] if ids else None
            self.show_reward = False

    # ── 布局 / 事件 ────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (vw - QUEST_WIN_W - 4, vh - LIST_H - BAR_RESERVE - 2)

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        if not self.rect.collidepoint(pos):
            return False
        for key, rect in self.tab_rects.items():
            if rect.collidepoint(pos):
                if key != self.tab:
                    self.tab = key
                    self.list_offset = 0
                    self.show_reward = False
                    self.detail_offset = 0
                return True
        if self.info_rect is not None and self.info_rect.collidepoint(pos):
            self.show_reward = not self.show_reward
            self.detail_offset = 0
            return True
        if self.giveup_rect is not None and self.giveup_rect.collidepoint(pos):
            self._abandon()
            return True
        for rect, qid in self.row_rects:
            if rect.collidepoint(pos):
                if qid != self.selected:
                    self.selected = qid
                    self.show_reward = False
                    self.detail_offset = 0
                return True
        return True

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        det = pygame.Rect(self.rect.left + LIST_W + GAP,
                          self.rect.top + BODY_TOP, DET_W, BODY_BOT - BODY_TOP)
        if det.collidepoint(pos):
            self.detail_offset = max(0, self.detail_offset + amount * 20)
            return True
        ids = self.quests_for_tab(self.tab)
        if len(ids) <= VISIBLE_ROWS:
            return self.rect.collidepoint(pos)
        lo = self.rect.left + 4
        hi = self.rect.left + LIST_W - 4
        if not (lo <= pos[0] <= hi and self.rect.top + LIST_TOP
                <= pos[1] <= self.rect.top + LIST_BOT):
            return False
        self.list_offset = max(0, min(len(ids) - VISIBLE_ROWS,
                                      self.list_offset + amount))
        return True

    def _abandon(self) -> None:
        qid = self.selected
        if qid is None:
            return
        abandon = getattr(self.svc.player().quests, "abandon", None)
        if abandon is not None:
            abandon(qid)
        self.selected = None
        self.show_reward = False
        self.detail_offset = 0

    # ── 文本 ───────────────────────────────────────────────────────
    def _clean(self, text: str) -> str:
        """纯文本路径（行名/标题）：脱全部标记，#c 物品码回退为物品名。"""
        a = self.svc.assets
        out = render_markup(text, map_name=a.map_name_of, npc_name=a.npc_name,
                            item_name=a.item_name, mob_name=a.mob_name_of)
        parts: List[str] = []
        for kind, val in split_item_icons(out):
            parts.append(val if kind == "t"
                         else a.item_name(str(val)) or f"#{val}")
        return "".join(parts)

    def _markup(self, text: str) -> str:
        """富文本路径（详情正文）：脱颜色/名称码但保留 #c 物品图标码。"""
        a = self.svc.assets
        return render_markup(text, map_name=a.map_name_of, npc_name=a.npc_name,
                             item_name=a.item_name, mob_name=a.mob_name_of)

    def _draw_rich_text(self, surface, x: int, y: int, text: str,
                        width: int, fs, color) -> int:
        """绘制一行（可含 \\n 与 #c 图标）并按宽折行，返回本行底部 y。

        行内元素先缓冲再统一落笔：行高取元素最大高度、全部底对齐，
        大物品图标不会压到上下文字行。
        """
        a = self.svc.assets
        base_h = fs.get_height()
        ty = y
        line: List[Tuple[pygame.Surface, int, int]] = []   # (surf, h, 右间距)
        line_w, line_h = 0, base_h

        def flush() -> None:
            nonlocal line, line_w, line_h, ty
            px = x
            for surf, h, gap in line:
                surface.blit(surf, (px, ty + line_h - h))
                px += surf.get_width() + gap
            advance = line_h + 4
            line, line_w, line_h = [], 0, base_h
            ty += advance

        def add(surf: pygame.Surface, h: int, gap: int) -> None:
            nonlocal line_w, line_h
            w = surf.get_width()
            if line and line_w + w > width:
                flush()
            line.append((surf, h, gap))
            line_w += w + gap
            line_h = max(line_h, h)

        for kind, val in split_item_icons(text):
            if kind == "i":
                icon = a.item_icon(str(val))
                if icon is not None:
                    add(icon, icon.get_height(), 2)
                    continue
                val = a.item_name(str(val)) or f"#{val}"
            for ch in val:
                if ch == "\n":
                    if line:
                        flush()
                    else:
                        ty += base_h + 4
                    continue
                add(fs.render(ch, True, color), base_h, 0)
        if line:
            flush()
        return ty

    # ── 绘制：列表窗 ───────────────────────────────────────────────
    def draw(self, surface) -> None:
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        x, y = self.place(surface, (QUEST_WIN_W, LIST_H))
        dx = x + LIST_W + GAP

        bg = widgets.wz_surface(self.svc, "Quest/backgrnd")
        if bg is not None:
            surface.blit(bg, (x, y))
        else:
            widgets.panel_frame(surface, pygame.Rect(x, y, LIST_W, LIST_H))
        self.add_chrome(surface, x, y, LIST_W, 12)

        ids = self.quests_for_tab(self.tab)
        self._ensure_selection(ids)
        self.list_offset = max(0, min(max(0, len(ids) - VISIBLE_ROWS),
                                      self.list_offset))

        self._draw_tabs(surface, x, y, fs)
        self._draw_rows(surface, x, y, ids, fs)

        det_bg = widgets.wz_surface(self.svc, "Quest/backgrnd2")
        if det_bg is not None:
            surface.blit(det_bg, (dx, y))
        else:
            widgets.panel_frame(surface, pygame.Rect(dx, y, DET_W, DET_H))
        qid = self.selected
        d = self.svc.player().quests.defs.get(qid) if qid else None
        if d is None:
            tip = fs.render("选择左侧任务查看详情", True, (120, 108, 92))
            surface.blit(tip, (dx + 24, y + 130))
            self.info_rect = self.giveup_rect = None
            return
        self._draw_detail_header(surface, dx, y, d, qid, f, fs)
        self._draw_detail_body(surface, dx, y, qid, fs)
        self._draw_detail_buttons(surface, dx, y, fs)

    def _draw_tabs(self, surface, x: int, y: int, fs) -> None:
        self.tab_rects.clear()
        tx = x + 4
        ty = y + 26
        for key in TAB_KEYS:
            ti = TAB_INDEX[key]
            state = "enabled" if key == self.tab else "disabled"
            img = widgets.wz_surface(self.svc, f"Quest/Tab/{state}/{ti}")
            if img is not None:            # 文字已烤死在底图，直接原样贴
                rect = pygame.Rect(tx, ty, img.get_width(), img.get_height())
                surface.blit(img, rect.topleft)
            else:
                label = TAB_LABEL[key]
                rect = pygame.Rect(tx, ty, fs.size(label)[0] + 12, 15)
                pygame.draw.rect(surface, HEADER_BLUE if key == self.tab
                                 else (196, 202, 212), rect)
                pygame.draw.rect(surface, (120, 132, 148), rect, 1)
                surface.blit(fs.render(label, True, (255, 255, 255)
                                       if key == self.tab else (90, 96, 110)),
                             (rect.x + 6, rect.y + 2))
            self.tab_rects[key] = rect
            tx = rect.right + 6

    def _draw_rows(self, surface, x: int, y: int, ids: List[str], fs) -> None:
        self.row_rects.clear()
        defs = self.svc.player().quests.defs
        row_w = LIST_W - 14
        for j in range(VISIBLE_ROWS):
            i = self.list_offset + j
            if i >= len(ids):
                break
            qid = ids[i]
            rect = pygame.Rect(x + 4, y + LIST_TOP + j * ROW_H, row_w, ROW_H)
            sel = qid == self.selected
            if sel:
                pygame.draw.rect(surface, HEADER_BLUE, rect)
            name = widgets.ellipsize(self._clean(defs[qid].name), fs,
                                     row_w - 8)
            surface.blit(fs.render(name, True, (255, 255, 255) if sel
                                   else (60, 52, 44)),
                         (rect.x + 4, rect.y + (ROW_H - fs.get_height()) // 2))
            self.row_rects.append((rect, qid))
        if len(ids) > VISIBLE_ROWS:
            track = pygame.Rect(x + LIST_W - 8, y + LIST_TOP, 5,
                                VISIBLE_ROWS * ROW_H)
            n = (VISIBLE_ROWS * track.height) // len(ids)
            thumb = pygame.Rect(track.x,
                                track.y + (track.height - n) * self.list_offset
                                // max(1, len(ids) - VISIBLE_ROWS),
                                track.width, max(n, 12))
            pygame.draw.rect(surface, (176, 186, 198), track, border_radius=2)
            pygame.draw.rect(surface, (110, 122, 140), thumb, border_radius=2)

    # ── 绘制：详情窗 ───────────────────────────────────────────────
    def _draw_detail_header(self, surface, dx: int, y: int, d, qid: str,
                            f, fs) -> None:
        if widgets.wz_surface(self.svc, "Quest/backgrnd2") is None:
            pygame.draw.rect(surface, HEADER_BLUE,
                             pygame.Rect(dx + 8, y + 28, DET_W - 16, 90))
        name = widgets.ellipsize(self._clean(d.name), f, 150)
        surface.blit(f.render(name, True, (255, 255, 255)), (dx + 32, y + 40))
        ty = y + 58
        surface.blit(fs.render(self._level_text(d), True, (235, 242, 248)),
                     (dx + 24, ty))
        ty += 16
        surface.blit(fs.render(self._job_text(d), True, (235, 242, 248)),
                     (dx + 24, ty))
        chain = self._chain_text(d)
        if chain is not None:
            ty += 16
            surface.blit(fs.render(chain, True, (222, 210, 245)),
                         (dx + 24, ty))
        self._draw_gauge(surface, dx, y, qid, d)
        self._draw_npc_portrait(surface, dx, y, d)

    @staticmethod
    def _level_text(d) -> str:
        if d.lvmin and d.lvmax:
            return f"等级 {d.lvmin}~{d.lvmax}"
        if d.lvmin:
            return f"等级 {d.lvmin}以上"
        if d.lvmax:
            return f"等级 {d.lvmax}以下"
        return "等级不限"

    @staticmethod
    def _job_text(d) -> str:
        if not d.jobs:
            return "全职业都可以"
        names = [JOBS[j].name if j in JOBS else f"职业{j}" for j in d.jobs]
        return " / ".join(names)

    def _chain_text(self, d) -> Optional[str]:
        if not d.parent:
            return None
        defs = self.svc.player().quests.defs
        siblings = [q for q, o in defs.items() if o.parent == d.parent]
        if len(siblings) <= 1:
            return None
        idx = sum(1 for q in siblings if defs[q].order <= d.order)
        return f"连续任务 ( {idx} / {len(siblings)} )"

    def _draw_gauge(self, surface, dx: int, y: int, qid: str, d) -> None:
        """进行中任务的完成进度条（击杀+收集），无进度数据或无目标不画。"""
        player = self.svc.player()
        quests = player.quests
        total = sum(c for _, c in d.kills) + sum(c for _, c in d.end_items)
        if not total or self.tab != "active":
            return
        done = 0
        for mid, c in d.kills:
            done += min(quests.kill_progress(qid, mid), c)
        for iid, c in d.end_items:
            prog = getattr(quests, "item_progress", None)
            done += min(prog(player, qid, iid), c) if prog else 0
        gx, gy, gw = dx + 24, y + 88, 130
        frame = widgets.wz_surface(self.svc, "Quest/Gauge/frame")
        fill = widgets.wz_surface(self.svc, "Quest/Gauge/gauge")
        if frame is not None and fill is not None:
            inner = pygame.Rect(gx, gy, gw, frame.get_height())
            surface.blit(frame, inner.topleft)
            w = int((gw - 4) * done / total)
            if w > 0:
                surface.blit(pygame.transform.scale(fill, (w, fill.get_height())),
                             (inner.x + 2, inner.y + 2))
        else:
            pygame.draw.rect(surface, (40, 60, 84), (gx, gy, gw, 8))
            pygame.draw.rect(surface, (120, 210, 120),
                             (gx, gy, int(gw * done / total), 8))
        txt = f"{done}/{total}"
        surface.blit(self.svc.ui.font_small.render(txt, True, (0, 0, 0)),
                     (gx + gw + 6, gy + 1))

    def _draw_npc_portrait(self, surface, dx: int, y: int, d) -> None:
        npc_id = d.end_npc if d.end_npc is not None else d.start_npc
        if npc_id is None:
            return
        getter = getattr(self.svc.assets, "npc_frames", None)
        if getter is None:
            return
        try:
            frames = getter(str(npc_id), "stand")
        except Exception:
            frames = []
        if not frames:
            return
        img = frames[0][0]
        box_w, box_h = 100, 84
        scale = min(1.0, box_w / img.get_width(), box_h / img.get_height())
        if scale < 1.0:
            img = pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * scale)),
                      max(1, int(img.get_height() * scale))))
        bx = dx + 190 + (DET_W - 190 - 8 - box_w) // 2
        surface.blit(img, (bx + (box_w - img.get_width()) // 2,
                           y + 118 - img.get_height() - 4))

    def detail_chunks(self, qid: str) -> List[str]:
        """详情正文行序列：奖励视图，或说明（+进行中的动态目标行，去重静态行）。"""
        d = self.svc.player().quests.defs.get(qid)
        if d is None:
            return []
        chunks: List[str] = []
        if self.show_reward:
            chunks.append("—— 完成奖励 ——")
            if d.reward_exp:
                chunks.append(f"经验：{d.reward_exp}")
            if d.reward_money:
                chunks.append(f"金币：{d.reward_money}")
            for iid, cnt in d.reward_items:
                if cnt <= 0:
                    continue
                nm = self.svc.assets.item_name(str(iid)) or str(iid)
                chunks.append(f"#c{iid}# {nm} ×{cnt}")
            return chunks
        desc = (d.desc0 if self.tab == "ready"
                else d.desc2 if self.tab == "done" else d.desc1)
        goals: List[str] = []
        if self.tab == "active" and self.svc.quest_goal_lines is not None:
            goals = self.svc.quest_goal_lines(qid) or []
        if desc:
            # 仅当动态行会逐条列出击杀/收集目标时才剔静态行；否则静态行是唯一目标信息
            dup = bool(d.kills or d.end_items)
            chunks.append(strip_static_goal_lines(desc) if (goals and dup) else desc)
        chunks.extend(goals)
        return chunks

    def _draw_detail_body(self, surface, dx: int, y: int, qid: str,
                          fs) -> None:
        width = DET_W - 40
        top = y + BODY_TOP
        view_h = BODY_BOT - BODY_TOP
        chunks = self.detail_chunks(qid)
        scratch = pygame.Surface((DET_W - 20, 4000), pygame.SRCALPHA)
        ty = 0
        for text in chunks:
            ty = self._draw_rich_text(scratch, 10, ty, self._markup(text),
                                      width, fs, (70, 62, 52)) + 2
        max_off = max(0, min(ty - view_h, scratch.get_height() - view_h))
        self.detail_offset = max(0, min(self.detail_offset, max_off))
        h = min(view_h, scratch.get_height() - self.detail_offset)
        surface.blit(scratch, (dx + 10, top),
                     pygame.Rect(0, self.detail_offset, DET_W - 20, h))
        if max_off > 0:
            track = pygame.Rect(dx + DET_W - 12, top, 5, view_h)
            n = max(12, view_h * view_h // ty)
            thumb = pygame.Rect(track.x,
                                track.y + (view_h - n) * self.detail_offset // max_off,
                                track.width, n)
            pygame.draw.rect(surface, (176, 186, 198), track, border_radius=2)
            pygame.draw.rect(surface, (110, 122, 140), thumb, border_radius=2)

    def _draw_detail_buttons(self, surface, dx: int, y: int, fs) -> None:
        by = y + DET_H - 26
        gx = dx + DET_W - 8 - BTN_W
        self.giveup_rect = None
        img = widgets.wz_surface(self.svc, "Quest/BtDetail/normal/0")
        rect = pygame.Rect(gx - 6 - BTN_W, by, BTN_W, BTN_H)
        if img is not None:
            surface.blit(img, rect.topleft)
        else:
            pygame.draw.rect(surface, (150, 158, 172), rect, border_radius=3)
            label = "任务资讯"
            surface.blit(fs.render(label, True, (30, 34, 44)),
                         (rect.x + (BTN_W - fs.size(label)[0]) // 2,
                          rect.y + 2))
        self.info_rect = rect
        if self.tab == "active":
            img = widgets.wz_surface(self.svc, "Quest/BtGiveup/normal/0")
            rect = pygame.Rect(gx, by, BTN_W, BTN_H)
            if img is not None:
                surface.blit(img, rect.topleft)
            else:
                pygame.draw.rect(surface, (172, 138, 120), rect, border_radius=3)
                label = "放弃"
                surface.blit(fs.render(label, True, (44, 30, 26)),
                             (rect.x + (BTN_W - fs.size(label)[0]) // 2,
                              rect.y + 2))
            self.giveup_rect = rect
