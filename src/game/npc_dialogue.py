"""NPC 对话控制器：把游戏循环里的「与 NPC 交互」编排收拢成一个类。

对话状态统一为单一 `self._conv: Conversation`（通用步骤图会话）：

· try_talk()        找脚下的 NPC 并路由（talk() 脚本 > 默认会话 > 直开商店 > 寒暄气泡）
· consume_click()   鼠标是否被对话层消费（链接/按钮/气泡关闭）
· consume_keydown() 回车/空格/Esc 是否被对话层消费
· update()          走远自动收起各对话框
· close_all()       切图 / 重生 / 进入任务前清空
· portal_blocked()  是否有对话框屏蔽传送门

NPC 有 `content/npc/<id>.lua` 的 `talk(ctx)` 则完全接管对话；Lua 驱动任务
（QuestDef.script 非空，如转职 advance.lua）同走 `_open_script_conv` 通道。
无 talk() 脚本的 NPC 走模块级 `build_menu_conversation` 合成的默认会话：
任务（可交付/可接/进行中）、出租车传送、商店入口折成一张蓝字列表；
任务链接点开 `quest_flow.build_quest_conversation` 的子会话。
        链接的传送/商店副作用不直接执行，只登记意图（_next_warp/_next_shop，
        脚本会话则经宿主 ctx.pending_warp/pending_shop 由 teleport()/open_shop() 登记），
由 `_after_turn` 在会话关闭后统一消费。
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Callable, List, Optional, Tuple

import pygame

from game import settings
from game.systems import dialogues
from game.systems.conversation import (
    Conversation, ConversationDef, Link, Step, make_ctx_view)
from game.systems.quest_flow import build_quest_conversation
from game.systems.quests import NpcQuest, collect_npc_quests, render_markup
from game.systems.script_api import make_globals
from game.systems.shop import STORAGE_NPC, shops_of
from game.core import travel
from game.core.jobs import JOBS, job_for_trainer

# 对话层「消费」某次点击后，game.py 不再把该事件交给商店/面板
# 玩家走远超过该横坐标距离即自动收起对话
TALK_RANGE = 140

# 内容脚本目录：resources/content/<script>.lua（talk() 契约见 content/AGENTS.md）
_CONTENT_DIR = settings.RESOURCE_DIR / "content"


# ═══ 默认会话合成 ═══════════════════════════════════════════════════

def build_menu_conversation(npc_name: str, map_id: str,
                            quests: List[NpcQuest],
                            teleports: List[Tuple[str, str]],
                            accepted: List[NpcQuest],
                            has_shop: bool, *,
                            on_quest: Callable[[NpcQuest], None],
                            on_teleport: Callable[[str], None],
                            on_shop: Callable[[], None]) -> Conversation:
    """无 talk() 脚本 NPC 的默认会话：任务/进行中/传送/商店合一张蓝字列表。

    链接顺序 = 可交付在前、可接在后（稳定排序）→ 进行中 → 传送（剔除当前图）
    → 商店。``on_*`` 只登记意图并返回 None → 链接点击即结束本菜单会话，
    由控制器在 `_after_turn` 里消费意图（打开子会话 / 切图 / 开店）。
    """
    links: List[Link] = []
    ordered = sorted(quests, key=lambda it: 0 if it.state == "complete" else 1)
    for item in ordered:
        links.append(Link(item.title, item.level,
                          click=lambda it=item: _intent(on_quest, it)))
    for item in accepted:
        links.append(Link(f"{item.title}（进行中）", item.level,
                          click=lambda it=item: _intent(on_quest, it)))
    for label, mid in teleports:
        if str(mid) == str(map_id):
            continue
        links.append(Link(label, click=lambda m=mid: _intent(on_teleport, m)))
    if has_shop:
        links.append(Link("商店", click=lambda: _intent(on_shop)))
    title = npc_name if quests or accepted else f"{npc_name} · 要去哪里？"
    steps = {"menu": Step(links=links)}
    return Conversation(ConversationDef(title, "menu", steps))


def _intent(fn: Callable, *args) -> None:
    """登记意图的链接回调：执行 hook 并返回 None（结束本会话）。"""
    fn(*args)
    return None


class NpcDialogueController:
    """管理一次 NPC 对话的完整状态机（非模态，不暂停世界）。"""

    def __init__(self, ctx, quest_defs: dict):
        self.ctx = ctx
        self.assets = ctx.assets
        self.quest_defs = quest_defs

        self._talk_npc: Optional[object] = None        # 当前寒暄气泡的 NPC
        # 统一会话状态：talk() 脚本会话 / 默认菜单 / 任务子会话
        self._conv: Optional[Conversation] = None
        self._conv_npc: Optional[object] = None        # 会话锚点 NPC（距离收起）
        self._conv_host: Optional[Any] = None          # 脚本会话宿主 ctx
        self._conv_qid: Optional[str] = None           # 脚本会话所属任务（转职善后）
        self._next_warp: Optional[str] = None          # 会话登记的传送意图
        self._next_shop: bool = False                  # 会话登记的开店意图
        # warp 由 Game 注入（map_id → 切图），本控制器不感知加载细节。
        self.warp: Optional[Callable[[str], None]] = None

    # ── 入口：找 NPC 并路由 ─────────────────────────────────────────
    def try_talk(self) -> None:
        """与脚下 NPC 对话：talk() 脚本 > 默认会话（任务/传送/商店链接）> 直开商店 > 寒暄。"""
        for npc in self.ctx.world.npcs:
            if npc.rect().colliderect(
                    pygame.Rect(int(self.ctx.world.player.x - 20),
                                int(self.ctx.world.player.y - 40), 40, 80)):
                if self._open_npc_talk(npc):
                    return
                self._talk_npc = npc
                qlist = collect_npc_quests(
                    self.quest_defs, self.ctx.world.player.quests,
                    str(npc.npc_id), self.ctx.world.player)
                dests = travel.teleports_of(npc.npc_id, self.ctx.assets.map_id)
                in_progress = self._accepted_at(npc)
                has_shop = bool(shops_of(npc.npc_id))
                if qlist or dests or in_progress:
                    conv = build_menu_conversation(
                        npc.name, str(self.ctx.assets.map_id), qlist, dests,
                        in_progress, has_shop,
                        on_quest=lambda it: self._open_quest_conv(npc, it),
                        on_teleport=self._request_warp,
                        on_shop=self._request_shop)
                    self._set_conv(conv, npc)
                    return
                if has_shop:
                    # 有商店且无任务/传送 → 直接开店，不再经气泡按钮
                    self.ctx.windows.get("storage").close()
                    self.ctx.windows.get("shop").open(npc.npc_id)
                    return
                buttons: List[str] = []
                if npc.npc_id == STORAGE_NPC:
                    buttons.append("storage")
                self.ctx.ui.show_dialog(npc.name,
                                    dialogues.get_dialog(npc.npc_id, npc.name),
                                    anchor=npc, buttons=buttons or None)
                return

    # ── 输入路由 ─────────────────────────────────────────────────────
    def consume_click(self, pos: Tuple[int, int]) -> bool:
        """鼠标左键是否被对话层消费（返回 True 时 game.py 不再转交面板/商店）。

        优先序：会话（链接 > 按钮 > 点外关闭）> 商店/仓库按钮 > 点击气泡关闭。
        """
        if self._conv is not None:
            idx = self.ctx.ui.conv.link_hit(pos)
            if idx is not None:
                self._conv.click_link(idx)
                self._after_turn()
            else:
                btn = self.ctx.ui.conv.button_hit(pos)
                if btn is not None:
                    self._conv.press(btn)
                    self._after_turn()
                elif not self.ctx.ui.conv.panel_hit(pos):
                    self._close_conv()   # 点面板外 → 收起会话
            return True
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
        if self._conv is not None:
            if key == pygame.K_ESCAPE:
                self._conv.press("close")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._conv.press("confirm")
            else:
                return True                 # 会话打开时吃掉其它键
            self._after_turn()
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
        # 寒暄气泡在走远后收起
        if self.ctx.ui.dialog_visible and self._talk_npc is not None:
            if abs(player.x - self._talk_npc.rect().centerx) > TALK_RANGE:
                self.ctx.ui.hide_dialog()
                self._talk_npc = None
        # 统一会话：按锚点 NPC 距离收起
        if self._conv is not None and self._conv_npc is not None:
            if abs(player.x - self._conv_npc.rect().centerx) > TALK_RANGE:
                self._close_conv()

    # ── 绘制 / 清理 / 查询 ──────────────────────────────────────────
    def close_all(self) -> None:
        self.ctx.ui.hide_dialog()
        self._talk_npc = None
        self._close_conv()

    def portal_blocked(self) -> bool:
        return self.ctx.ui.conv.visible or self.ctx.ui.dialog_visible

    # ── 会话生命周期 ────────────────────────────────────────────────
    def _accepted_at(self, npc) -> List[NpcQuest]:
        """该 NPC 名下已接取、但尚不可交付的任务（默认会话的「进行中」链接）。"""
        quests = self.ctx.world.player.quests
        out: List[NpcQuest] = []
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == str(npc.npc_id) \
                    and quests.is_accepted(qid) \
                    and not quests.can_complete(qid, self.ctx.world.player):
                out.append(NpcQuest(qid=qid, title=d.name, level=d.lvmin,
                                    state="accepted"))
        return out

    def _open_quest_conv(self, npc, item: NpcQuest) -> None:
        """任务链接 → 子会话（offer/complete/status）；Lua 驱动任务走 talk() 脚本。"""
        d = self.quest_defs.get(item.qid)
        if d is None:
            return
        if d.script:   # 转职 adv_*：content/<script>.lua 的 talk() 会话；失败则不开
            self._open_script_conv(npc, item.qid, d.script)
            return
        stage = "status" if item.state == "accepted" else item.state
        conv = build_quest_conversation(
            item.qid, stage, d=d, log=self.ctx.world.player.quests,
            player=self.ctx.world.player, combat=self.ctx.world.combat,
            assets=self.assets, audio=self.ctx.audio,
            notify=self.ctx.windows.flash, qmark=self._qmark)
        self._set_conv(conv, npc)

    def _set_conv(self, conv: Conversation, npc, host: Optional[Any] = None,
                  qid: Optional[str] = None) -> None:
        """装载新会话（替换当前 `_conv` 及其宿主绑定）并立即渲染；关掉寒暄气泡。"""
        self._conv = conv
        self._conv_npc = npc
        self._conv_host = host
        self._conv_qid = qid
        self.ctx.ui.hide_dialog()
        self._talk_npc = None
        self._show_conv()

    def _show_conv(self) -> None:
        """渲染当前快照；文本统一过官方标记解析（#t#o#m#p、#b/#r、\\n）。

        适配器（quest_flow）已 qmark 过的文本不含残留标记，重复解析无损。
        """
        snap = self._conv.current()
        self.ctx.ui.conv.show(snap.title,
                              [self._qmark(l) for l in snap.lines],
                              [(self._qmark(label), note)
                               for label, note in snap.links],
                              snap.buttons, snap.terminal)

    def _close_conv(self) -> None:
        self.ctx.ui.conv.hide()
        self._conv = None
        self._conv_npc = None
        self._conv_host = None
        self._conv_qid = None

    def _request_warp(self, map_id: str) -> None:
        self._next_warp = map_id

    def _request_shop(self) -> None:
        self._next_shop = True

    def _after_turn(self) -> None:
        """一次交互（链接/按钮/按键）后的统一善后：意图 > 结束 > 重绘。"""
        host = self._conv_host
        if host is not None and getattr(host, "pending_shop", None):
            host.pending_shop = None
            self._next_shop = True
        if self._next_warp:
            w, self._next_warp = self._next_warp, None
            self._close_conv()
            if self.warp is not None:
                self.warp(w)
            return
        if self._next_shop:
            self._next_shop = False
            npc = self._conv_npc
            self._close_conv()
            self.ctx.windows.get("storage").close()
            if npc is not None:
                self.ctx.windows.get("shop").open(npc.npc_id)
            return
        if host is not None and getattr(host, "pending_warp", None):
            w = host.pending_warp
            host.pending_warp = None
            self._close_conv()
            if self.warp is not None:
                self.warp(w)
            return
        if self._conv is not None and self._conv.done:
            self._finish_conv()
        elif self._conv is not None:
            self._show_conv()

    def _finish_conv(self) -> None:
        """会话正常结束（done）时的善后：转职音效/灯泡/force_complete。"""
        if (self._conv_qid is not None and self._conv_host is not None
                and self._conv_host.advanced):
            self.ctx.audio.play("LevelUp", 0.6)
            self.ctx.windows.flash(
                f"转职成功：{JOBS[self.ctx.world.player.job].name}")
            # 转职任务完成：置为已完成，不再出现在可接列表
            self.ctx.world.player.quests.force_complete(self._conv_qid)
        self._close_conv()

    def _dialog_button(self, key: str) -> None:
        """NPC 对话按钮回调：打开仓库面板。"""
        npc = self._talk_npc
        self.ctx.ui.hide_dialog()
        self._talk_npc = None
        if npc is None:
            return
        if key == "storage":
            self.ctx.windows.get("shop").close()
            self.ctx.windows.get("storage").open()

    # ── Lua 脚本会话（talk() 契约）───────────────────────────────────
    def _host_ctx(self, npc, jobdef=None) -> Any:
        """脚本会话的宿主 ctx：script_api 闭包读它，teleport/open_shop 登记意图。"""
        return SimpleNamespace(player=self.ctx.world.player,
                               world=self.ctx.world, jobdef=jobdef,
                               assets=self.assets, npc_name=npc.name,
                               quest_defs=self.quest_defs,
                               advanced=False, pending_warp=None,
                               pending_shop=None)

    def _open_script_conv(self, npc, qid: Optional[str],
                          script_name: str) -> bool:
        """content/<script>.lua 的 talk() 会话；失败返回 False 由调用方回落。"""
        path = _CONTENT_DIR / f"{script_name}.lua"
        if not path.is_file():
            return False
        host = self._host_ctx(npc, jobdef=job_for_trainer(
            npc.npc_id, self.ctx.world.player.job))
        ctx_view = make_ctx_view(host.player, npc.npc_id, npc.name,
                                 self.assets.map_id, jobdef=host.jobdef)
        try:
            conv = Conversation.from_source(path.read_text("utf-8"),
                                            make_globals(host), ctx_view,
                                            title=npc.name)
        except Exception:
            logging.warning("对话脚本 %s 加载失败", script_name, exc_info=True)
            return False
        self._set_conv(conv, npc, host=host, qid=qid)
        return True

    def _open_npc_talk(self, npc) -> bool:
        """NPC 自带 talk() 脚本（content/npc/<id>.lua）则接管对话，最高优先级。"""
        return self._open_script_conv(npc, None, f"npc/{npc.npc_id}")

    # ── 文本标记渲染 ────────────────────────────────────────────────
    def _qmark(self, text: str) -> str:
        """把官方 Say 文本里的标记替换为可读文本。"""
        a = self.assets
        return render_markup(text, a,
                             map_name=a.map_name_of, npc_name=a.npc_name,
                             item_name=a.item_name, mob_name=a.mob_name_of)
