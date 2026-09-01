"""NPC 对话控制器：把游戏循环里的「与 NPC 交互」编排收拢成一个类。

原来这段逻辑散布在 game.py：`_try_talk`、任务流程状态机、转职会话、任务列表
菜单、寒暄气泡的按钮/按键路由、走动收起。本控制器持有全部对话状态（当前 NPC、
任务流程、转职会话、多任务列表），并暴露游戏循环需要的最小入口：

· try_talk()        找脚下的 NPC 并路由（转职 > 任务列表/直连 > 寒暄）
· consume_click()   鼠标是否被对话层消费（列表/按钮/气泡关闭）
· consume_keydown() 回车/空格/Esc 是否被对话层消费
· update()          走远自动收起各对话框
· draw()            绘制任务选择列表覆盖层
· close_all()       切图 / 重生 / 进入任务前清空
· portal_blocked()  是否有对话框屏蔽传送门

逻辑全部建于已抽出的声明式层：转职走 scripting.LuaSession 会话、任务列表走
render.quest_alarm.QuestAlarmView、任务过滤走 quests.collect_npc_quests —— 本类
只做编排与路由，不再硬编码任何对话文案。
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import pygame

from game import settings
from game.render.quest_alarm import QuestAlarm, QuestAlarmView, QuestEntry, PANEL_W
from game.systems import dialogues
from game.systems.quests import collect_npc_quests, render_markup
from game.systems.scripting import build_lua_session
from game.systems.shop import SHOP_NPCS, STORAGE_NPC
from game.core.jobs import JOBS, job_for_trainer

# 对话层「消费」某次点击后，game.py 不再把该事件交给商店/面板
# 玩家走远超过该横坐标距离即自动收起对话
TALK_RANGE = 140


class NpcDialogueController:
    """管理一次 NPC 对话的完整状态机（非模态，不暂停世界）。"""

    def __init__(self, ctx, quest_defs: dict):
        self.ctx = ctx
        self.assets = ctx.assets
        self.quest_defs = quest_defs

        self._talk_npc: Optional[object] = None        # 当前寒暄气泡的 NPC
        self._quest_flow: Optional[dict] = None        # 单任务流程 {npc,quest,stage}
        self._advance_session = None                   # 转职解说会话
        self._advance_ctx: Optional[Any] = None
        self._advance_npc: Optional[object] = None
        self._quest_menu_view: Optional[QuestAlarmView] = None   # 多任务选择列表
        self._quest_menu_items: List[object] = []
        self._quest_menu_npc: Optional[object] = None
        self._quest_menu_rect: Optional[Tuple[int, int]] = None  # 列表左上角

    # ── 入口：找 NPC 并路由 ─────────────────────────────────────────
    def try_talk(self) -> None:
        """与脚下 NPC 对话：导师转职 > 任务交互（列表/直连）> 普通寒暄。"""
        for npc in self.ctx.world.npcs:
            if npc.rect().colliderect(
                    pygame.Rect(int(self.ctx.world.player.x - 20),
                                int(self.ctx.world.player.y - 40), 40, 80)):
                self._talk_npc = npc
                jobdef = job_for_trainer(npc.npc_id)
                if jobdef is not None and self._begin_advance_flow(npc, jobdef):
                    return
                qlist = collect_npc_quests(
                    self.quest_defs, self.ctx.world.player.quests,
                    str(npc.npc_id), self.ctx.world.player)
                if qlist:
                    if len(qlist) == 1:
                        self._open_npc_quest(npc, qlist[0])
                    else:
                        self._open_quest_menu(npc, qlist)
                    return
                if self._begin_quest_flow(npc):   # 仅剩「进行中未满足」的状态提示
                    return
                buttons: List[str] = []
                if npc.npc_id in SHOP_NPCS:
                    buttons.append("shop")
                if npc.npc_id == STORAGE_NPC:
                    buttons.append("storage")
                self.ctx.ui.show_dialog(npc.name,
                                    dialogues.get_dialog(npc.npc_id, npc.name),
                                    anchor=npc, buttons=buttons or None)
                return

    # ── 输入路由 ─────────────────────────────────────────────────────
    def consume_click(self, pos: Tuple[int, int]) -> bool:
        """鼠标左键是否被对话层消费（返回 True 时 game.py 不再转交面板/商店）。

        优先序：多任务列表 > 任务框按钮 > 商店/仓库按钮 > 点击气泡关闭。
        """
        if self._quest_menu_view is not None:
            if self._quest_menu_rect is not None:
                idx = self._quest_menu_view.hit_index(
                    self.assets, self._quest_menu_rect[0], self._quest_menu_rect[1],
                    pos)
                if idx is not None:
                    item = self._quest_menu_items[idx]
                    npc = self._quest_menu_npc
                    self._close_quest_menu()
                    self._open_npc_quest(npc, item)
                else:
                    self._close_quest_menu()
            return True
        btn = self.ctx.ui.quest_hit(pos)
        if btn is not None:
            if self._advance_session is not None:
                self._advance_button(btn)
            else:
                self._quest_button(btn)
            return True
        if self.ctx.ui.quest_dialog_hit(pos):
            return True        # 点对话框空白处不关闭（选项型）
        dkey = self.ctx.ui.dialog_button_hit(pos)
        if dkey is not None:
            self._dialog_button(dkey)
            return True
        if self.ctx.ui.dialog_hit(pos):
            self.ctx.ui.hide_dialog()   # 点击气泡本体 → 关闭对话
            self._talk_npc = None
            return True
        return False

    def consume_keydown(self, key: int) -> bool:
        """回车/空格/Esc 是否被对话层消费；否则交回 game.py（移动/商店等）。"""
        if self.ctx.ui.quest_visible:
            qkey = None
            if key == pygame.K_ESCAPE:
                qkey = "close"
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                qkey = "confirm"
            if qkey is not None:
                if self._advance_session is not None:
                    self._advance_button(qkey)
                elif self._quest_flow is not None \
                        and self._quest_flow["stage"] in ("offer", "complete"):
                    self._quest_button("no" if qkey == "close" else "yes")
                else:
                    self.ctx.ui.hide_quest()
                    self._quest_flow = None
                return True
        if self.ctx.ui.dialog_visible:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                       pygame.K_SPACE, pygame.K_ESCAPE):
                self.ctx.ui.hide_dialog()
                self._talk_npc = None
                return True
        return False

    # ── 每帧：走远自动收起 ──────────────────────────────────────────
    def update(self) -> None:
        player = self.ctx.world.player
        # 寒暄气泡 / 任务框在走远后收起
        if self.ctx.ui.dialog_visible and self._talk_npc is not None:
            if abs(player.x - self._talk_npc.rect().centerx) > TALK_RANGE:
                self.ctx.ui.hide_dialog()
                self._talk_npc = None
        if self.ctx.ui.quest_visible:
            npc = (self._advance_npc if self._advance_session is not None
                   else self._quest_flow["npc"] if self._quest_flow is not None
                   else None)
            if npc is not None and abs(player.x - npc.rect().centerx) > TALK_RANGE:
                self.ctx.ui.hide_quest()
                self._quest_flow = None
                self._advance_session = None
                self._advance_npc = None
        if self._quest_menu_view is not None and self._quest_menu_npc is not None:
            if abs(player.x - self._quest_menu_npc.rect().centerx) > TALK_RANGE:
                self._close_quest_menu()

    # ── 绘制 / 清理 / 查询 ──────────────────────────────────────────
    def draw(self, surface) -> None:
        if self._quest_menu_view is None or self._quest_menu_rect is None:
            return
        self._quest_menu_view.draw(surface, self.assets,
                                   self._quest_menu_rect[0], self._quest_menu_rect[1])

    def close_all(self) -> None:
        self.ctx.ui.hide_dialog()
        self.ctx.ui.hide_quest()
        self._talk_npc = None
        self._quest_flow = None
        self._advance_session = None
        self._advance_ctx = None
        self._advance_npc = None
        self._close_quest_menu()

    def portal_blocked(self) -> bool:
        return self.ctx.ui.quest_visible or self.ctx.ui.dialog_visible

    # ── 单任务接取/交付 ─────────────────────────────────────────────
    def _open_npc_quest(self, npc, item) -> None:
        """进入单个任务的接取/交付流程（item 为 collect_npc_quests 的 NpcQuest）。"""
        self._quest_flow = {"npc": npc, "quest": item.qid, "stage": item.state}
        if item.state == "complete":
            self._show_quest_complete(item.qid)
        else:
            self._show_quest_offer(item.qid)

    def _open_quest_menu(self, npc, items) -> None:
        """多个可接/可交付任务 → 弹原版 QuestAlarm 列表选择。"""
        entries = [QuestEntry(title=it.title, level=it.level) for it in items]
        model = QuestAlarm(entries=entries, per_page=5)
        self._quest_menu_view = QuestAlarmView(model)
        self._quest_menu_items = list(items)
        self._quest_menu_npc = npc
        n = len(model.visible())
        self._quest_menu_rect = ((settings.VIEW_W - PANEL_W) // 2,
                                 settings.VIEW_H // 2
                                 - self._quest_menu_view.panel_height(n) // 2)

    def _close_quest_menu(self) -> None:
        self._quest_menu_view = None
        self._quest_menu_items = []
        self._quest_menu_npc = None
        self._quest_menu_rect = None

    def _dialog_button(self, key: str) -> None:
        """NPC 对话按钮回调：打开商店 / 仓库面板。"""
        npc = self._talk_npc
        self.ctx.ui.hide_dialog()
        self._talk_npc = None
        if npc is None:
            return
        if key == "shop":
            self.ctx.storage_panel.close()
            self.ctx.shop_panel.open(npc.npc_id)
        elif key == "storage":
            self.ctx.shop_panel.close()
            self.ctx.storage_panel.open()

    # ── 转职对话（内容脚本在 content/advance.lua）──────────────────────
    def _begin_advance_flow(self, npc, jobdef) -> bool:
        """导师对话：由 Lua 会话按玩家状态路由（可转职/已是该职/不足）。"""
        sess, ctx = build_lua_session(
            "advance", player=self.ctx.world.player, jobdef=jobdef,
            npc_name=npc.name, assets=self.assets)
        self._advance_session = sess
        self._advance_ctx = ctx
        self._advance_npc = npc
        self._show_session_snapshot()
        return True

    def _show_session_snapshot(self) -> None:
        """把当前对话会话的快照（说话人/文本/选项）渲染到原版任务框。"""
        snap = self._advance_session.snapshot()
        self.ctx.ui.show_quest(snap.npc, snap.lines,
                               [o.label for o in snap.options])

    def _advance_button(self, key: str) -> None:
        """转职对话框按钮回调：yes / no / ok（或确认/关闭意图）。"""
        sess = self._advance_session
        if sess is None:
            self.ctx.ui.hide_quest()
            return
        labels = [o.label for o in sess.snapshot().options]
        if key == "confirm":
            target = "yes" if "yes" in labels else ("ok" if "ok" in labels else None)
        elif key == "close":
            target = "no" if "no" in labels else None
        else:
            target = key if key in labels else None
        if target is None:
            target = "ok"
        sess.choose(target)
        if sess.done:
            self.ctx.ui.hide_quest()
            self._advance_session = None
            self._advance_npc = None
            advanced = getattr(self._advance_ctx, "advanced", False)
            self._advance_ctx = None
            if advanced:
                self.ctx.audio.play("LevelUp", 0.6)
                self.ctx.panels.flash(
                    f"转职成功：{JOBS[self.ctx.world.player.job].name}")
            return
        self._show_session_snapshot()

    # ── 任务对话状态机 ─────────────────────────────────────────────
    def _begin_quest_flow(self, npc) -> bool:
        """检查与 NPC 的任务交互（进行中的状态提示）。返回是否进入对话框。"""
        quests = self.ctx.world.player.quests
        npc_id = npc.npc_id
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == npc_id \
                    and quests.is_accepted(qid):
                self._quest_flow = {"npc": npc, "quest": qid, "stage": "status"}
                self._show_quest_status(qid)
                return True
        return False

    def _qmark(self, text: str) -> str:
        """把官方 Say 文本里的标记替换为可读文本。"""
        a = self.assets
        return render_markup(text, a,
                             map_name=a.map_name_of, npc_name=a.npc_name,
                             item_name=a.item_name, mob_name=a.mob_name_of)

    def _show_quest_offer(self, qid: str) -> None:
        d = self.quest_defs[qid]
        lines = [self._qmark(l) for l in d.accept_lines] or [f"要接受任务「{d.name}」吗？"]
        self.ctx.ui.show_quest(f"任务 · {d.name}", lines, ["yes", "no"])

    def _show_quest_complete(self, qid: str) -> None:
        d = self.quest_defs[qid]
        lines = [self._qmark(l) for l in d.complete_lines] or [
            f"已完成任务「{d.name}」的所有条件！要领取奖励吗？"]
        self.ctx.ui.show_quest(f"任务完成 · {d.name}", lines, ["yes", "no"])

    def _show_quest_status(self, qid: str) -> None:
        d = self.quest_defs[qid]
        lines = [self._qmark(l) for l in d.complete_stop] or \
                [f"「{d.name}」还未完成，继续努力吧！"]
        self.ctx.ui.show_quest(d.name, lines, ["ok"])

    def _quest_button(self, key: str) -> None:
        """任务对话框按钮回调：yes / no / ok（转职已交由 _advance_button）。"""
        flow = self._quest_flow
        if flow is None:
            self.ctx.ui.hide_quest()
            return
        if self._advance_session is not None:
            self._advance_button(key)
            return
        qid = flow["quest"]
        quests = self.ctx.world.player.quests
        if flow["stage"] == "offer":
            if key == "yes":
                if quests.accept(qid, self.ctx.world.player):
                    d = self.quest_defs[qid]
                    self.ctx.audio.play("QuestClear", 0.5)
                    self.ctx.panels.flash(f"任务接受：{d.name}")
                    flow["stage"] = "accepted"
                    lines = [self._qmark(l) for l in d.accept_yes] or \
                            [f"已接受任务「{d.name}」。按 Q 查看任务日志。"]
                    self.ctx.ui.show_quest(d.name, lines, ["ok"])
                else:
                    self.ctx.ui.hide_quest()
            else:
                d = self.quest_defs[qid]
                flow["stage"] = "declined"
                lines = [self._qmark(l) for l in d.accept_no] or ["好吧，改变心意的话再来找我。"]
                self.ctx.ui.show_quest(d.name, lines, ["ok"])
        elif flow["stage"] == "complete":
            if key == "yes":
                if quests.complete(qid, self.ctx.world.player, self.ctx.world.combat,
                                   self.assets, self.ctx.audio):
                    d = self.quest_defs[qid]
                    self.ctx.panels.flash(f"任务完成：{d.name}")
                    flow["stage"] = "completed"
                    lines = [self._qmark(l) for l in d.complete_yes] or \
                            [f"已获得任务「{d.name}」的奖励！"]
                    self.ctx.ui.show_quest(d.name, lines, ["ok"])
                else:
                    self.ctx.ui.hide_quest()
            else:
                self.ctx.ui.hide_quest()
        else:   # status / accepted / declined / completed 只展示 → 关闭
            self.ctx.ui.hide_quest()
            self._quest_flow = None
