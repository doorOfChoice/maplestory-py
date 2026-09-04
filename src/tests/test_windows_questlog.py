"""QuestLogWindow 行为：空态 / 逐条绘制 / 目标回调 / 关闭与穿透（素材缺失 fallback 路径）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, List, Optional

from game.render.windows.questlog import BAR_RESERVE, QuestLogWindow
from tests.windows_harness import (close_button_pos, draw_once, make_manager,
                                   make_services, press)


# ── 测试数据助手 ───────────────────────────────────────────────────
def make_def(name: str, start_npc: Optional[int] = None,
             end_npc: Optional[int] = None):
    return SimpleNamespace(name=name, start_npc=start_npc, end_npc=end_npc)


def make_player(accepted: List[str], defs: dict):
    """假玩家：quests 只提供任务日志读取的三个成员。"""
    quests = SimpleNamespace(
        accepted_order=list(accepted),
        is_accepted=lambda qid: qid in accepted,
        defs=defs,
    )
    return SimpleNamespace(quests=quests)


def open_log(player, goal_lines: Optional[Callable[[str], List[str]]] = None) -> tuple:
    """装配可见的 QuestLogWindow 并绘制一帧。"""
    svc = make_services(player)
    svc.quest_goal_lines = goal_lines
    win = QuestLogWindow(svc)
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    return win, mgr


# ── 绘制不抛错 ─────────────────────────────────────────────────────
def test_empty_log_draws_without_error():
    """空态（无进行中任务）逐帧绘制不抛错。"""
    win, mgr = open_log(make_player([], {}))
    draw_once(mgr)
    assert win.visible


def test_active_quests_render_without_error():
    """有进行中任务时逐条绘制（含标记文本脱标签）不抛错。"""
    defs = {
        "q1": make_def("收集 #o100100# 的素材", start_npc=90001),
        "q2": make_def("拜访 #p90002# 交付 #t2000000#", start_npc=90002, end_npc=90003),
    }
    win, mgr = open_log(make_player(["q1", "q2"], defs),
                        goal_lines=lambda qid: [f"进度 {qid} 0/5"])
    draw_once(mgr)
    assert win.visible


# ── 目标回调与过滤 ─────────────────────────────────────────────────
def test_goal_lines_called_for_each_active_quest_in_order():
    """goal_lines 回调按接取顺序对每个进行中任务的 qid 各调一次。"""
    seen: List[str] = []
    defs = {
        "q1": make_def("任务一", start_npc=1),
        "q2": make_def("任务二", end_npc=2),
    }

    def goal_lines(qid: str) -> List[str]:
        seen.append(qid)
        return []

    open_log(make_player(["q1", "q2"], defs), goal_lines)
    assert seen == ["q1", "q2"]


def test_unaccepted_and_undefied_quests_are_skipped():
    """未接取（is_accepted False）与无定义的 qid 都不进绘制、不触发回调。"""
    seen: List[str] = []
    defs = {"q1": make_def("任务一", start_npc=1)}
    player = make_player(["ghost", "q1", "q2"], defs)
    player.quests.is_accepted = lambda qid: qid != "ghost"

    def goal_lines(qid: str) -> List[str]:
        seen.append(qid)
        return []

    svc = make_services(player)
    svc.quest_goal_lines = goal_lines
    win = QuestLogWindow(svc)
    win.open()
    draw_once(make_manager(win))
    assert seen == ["q1"]


def test_no_goal_lines_callback_still_draws():
    """svc.quest_goal_lines 为 None 时绘制不抛错。"""
    player = make_player(["q1"], {"q1": make_def("任务一", start_npc=90001)})
    win, mgr = open_log(player, None)
    draw_once(mgr)
    assert win.visible


# ── chrome / 事件 ──────────────────────────────────────────────────
def test_close_button_click_closes_questlog():
    """有 chrome：点关闭钮即关窗（经 manager 全链路）。"""
    win, mgr = open_log(make_player([], {}))
    assert win.close_rect is not None
    assert press(mgr, close_button_pos(win))
    assert not win.visible


def test_click_inside_log_consumed_and_outside_passes_through():
    """窗口内点击被消费（防穿透），窗口外穿透给世界。"""
    win, mgr = open_log(make_player([], {}))
    assert press(mgr, win.rect.center)
    assert not press(mgr, (5, 5))


def test_anchor_reserves_bottom_bar_height():
    """默认锚点右下，底部为状态栏预留 BAR_RESERVE。"""
    win, mgr = open_log(make_player([], {}))
    assert win.rect.x == 800 - win.rect.width - 4
    assert win.rect.bottom == 600 - BAR_RESERVE - 2
