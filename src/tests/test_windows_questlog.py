"""QuestLogWindow 行为：双联排（列表+详情）/ 页签过滤 / 行选中 / 放弃 / 滚动 / 关闭与穿透（素材缺失 fallback 路径）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Callable, List, Optional

from game.render.windows.questlog import (BAR_RESERVE, GAP, LIST_W,
                                          QUEST_WIN_W, QuestLogWindow,
                                          strip_static_goal_lines)
from tests.windows_harness import (close_button_pos, draw_once, make_manager,
                                   make_services, motion, press, wheel)


# ── 测试数据助手 ───────────────────────────────────────────────────
def make_def(name: str, start_npc: Optional[int] = None,
             end_npc: Optional[int] = None, lvmin: int = 0, lvmax: int = 0,
             desc0: str = "", desc1: str = "", desc2: str = ""):
    return SimpleNamespace(name=name, start_npc=start_npc, end_npc=end_npc,
                           lvmin=lvmin, lvmax=lvmax, jobs=[], desc0=desc0, desc1=desc1,
                           desc2=desc2, parent="", order=0,
                           reward_exp=0, reward_money=0, reward_items=[],
                           kills=[], end_items=[])


def make_player(accepted: List[str], defs: dict, ready: List[str] = (),
                completed: List[str] = ()):
    """假玩家：quests 提供任务日志读取/操作的全部公开成员。"""
    accepted = list(accepted)

    def abandon(qid: str) -> None:
        abandoned.append(qid)
        accepted.remove(qid)

    abandoned: List[str] = []
    quests = SimpleNamespace(
        accepted_order=accepted,
        is_accepted=lambda qid: qid in accepted,
        is_completed=lambda qid: qid in completed,
        can_start=lambda qid, player: qid in ready,
        abandon=abandon,
        abandoned=abandoned,
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


# ── 默认态与选中 ───────────────────────────────────────────────────
def test_empty_log_draws_without_error():
    """空态（无任何任务）逐帧绘制不抛错。"""
    win, mgr = open_log(make_player([], {}))
    draw_once(mgr)
    assert win.visible


def test_default_tab_is_active_and_selects_first():
    """默认停在「正在进行」页签并自动选中第一条；详情只对选中任务取目标行。"""
    seen: List[str] = []
    defs = {"q1": make_def("任务一", end_npc=1), "q2": make_def("任务二")}
    win, _ = open_log(make_player(["q1", "q2"], defs), seen.append)
    assert win.tab == "active"
    assert win.selected == "q1"
    assert seen == ["q1"]


def test_ghost_and_unaccepted_rows_are_skipped():
    """accepted_order 里未接取（is_accepted False）与无定义的 qid 都不进列表。"""
    defs = {"q1": make_def("任务一")}
    player = make_player(["ghost", "q1", "q2"], defs)
    win, _ = open_log(player)
    assert win.quests_for_tab("active") == ["q1"]


# ── 页签 ───────────────────────────────────────────────────────────
def test_quests_for_tab_uses_can_start_and_completed():
    """「可以开始」走 can_start 过滤，「完成」走 is_completed。"""
    defs = {"a": make_def("可接"), "b": make_def("进行中"), "c": make_def("完成")}
    win, _ = open_log(make_player(["b"], defs, ready=["a"], completed=["c"]))
    assert win.quests_for_tab("ready") == ["a"]
    assert win.quests_for_tab("done") == ["c"]


def test_ready_tab_sorts_level_required_first_desc():
    """可接页排序：有等级限制的排前、按等级从高到低，无等级限制的靠后。"""
    defs = {"a": make_def("无限制"), "b": make_def("十级", lvmin=10),
            "c": make_def("三十级", lvmin=30)}
    win, _ = open_log(make_player([], defs, ready=["a", "b", "c"]))
    assert win.quests_for_tab("ready") == ["c", "b", "a"]


def test_tab_click_switches_filter():
    """点击页签热区切换当前页签。"""
    defs = {"a": make_def("可接")}
    win, mgr = open_log(make_player([], defs, ready=["a"]))
    assert press(mgr, win.tab_rects["ready"].center)
    assert win.tab == "ready"


# ── 行选中与详情 ───────────────────────────────────────────────────
def test_row_click_selects_quest():
    """点击列表行选中对应任务。"""
    defs = {"q1": make_def("任务一"), "q2": make_def("任务二")}
    win, mgr = open_log(make_player(["q1", "q2"], defs))
    row_q2 = next(r for r, qid in win.row_rects if qid == "q2")
    assert press(mgr, row_q2.center)
    assert win.selected == "q2"


def test_detail_button_toggles_reward_view():
    """点 BtDetail（任务资讯）在说明与奖励视图间切换。"""
    defs = {"q1": make_def("任务一")}
    win, mgr = open_log(make_player(["q1"], defs))
    assert win.show_reward is False
    assert press(mgr, win.info_rect.center)
    assert win.show_reward is True


def test_normal_detail_body_excludes_rewards():
    """点行看详情：正文只有说明与目标行；奖励仅在「任务资讯」视图展示。"""
    d = make_def("任务一", desc1="去打怪")
    d.reward_exp, d.reward_money = 100, 500
    win, mgr = open_log(make_player(["q1"], {"q1": d}),
                        goal_lines=lambda qid: ["击杀 蓝宝 0/5"])
    press(mgr, next(r for r, qid in win.row_rects if qid == "q1").center)
    body = "\n".join(win.detail_chunks("q1"))
    assert "去打怪" in body and "击杀 蓝宝" in body and "奖励" not in body
    win.show_reward = True
    reward = "\n".join(win.detail_chunks("q1"))
    assert "经验：100" in reward and "金币：500" in reward


# ── 放弃 ───────────────────────────────────────────────────────────
def test_abandon_button_removes_quest():
    """进行中任务点放弃：调 QuestLog.abandon、清选中、列表移除。"""
    defs = {"q1": make_def("任务一")}
    player = make_player(["q1"], defs)
    win, mgr = open_log(player)
    assert press(mgr, win.giveup_rect.center)
    assert player.quests.abandoned == ["q1"]
    assert win.selected is None
    assert win.quests_for_tab("active") == []


def test_abandon_button_hidden_for_non_accepted():
    """可接 / 已完成任务不显示放弃按钮。"""
    defs = {"a": make_def("可接"), "c": make_def("完成")}
    win, _ = open_log(make_player([], defs, ready=["a"], completed=["c"]))
    assert win.giveup_rect is None
    win.tab = "done"
    draw_once(make_manager(win))
    assert win.giveup_rect is None


# ── 滚动 ───────────────────────────────────────────────────────────
def test_wheel_scrolls_list():
    """列表超过一屏时，滚轮移动 win.list_offset。"""
    defs = {f"q{i}": make_def(f"任务{i}") for i in range(40)}
    win, mgr = open_log(make_player([f"q{i}" for i in range(40)], defs))
    assert win.list_offset == 0
    assert wheel(mgr, win.row_rects[0][0].center, up=False)
    assert win.list_offset == 1


def test_mousewheel_event_dispatches_to_list():
    """真实 pygame.MOUSEWHEEL 事件走 dispatch：以最近鼠标位滚列表。"""
    import pygame

    defs = {f"q{i}": make_def(f"任务{i}") for i in range(40)}
    win, mgr = open_log(make_player([f"q{i}" for i in range(40)], defs))
    motion(mgr, win.row_rects[0][0].center)          # 记录鼠标所在行
    assert mgr.dispatch(pygame.event.Event(pygame.MOUSEWHEEL, y=-1))
    assert win.list_offset == 1


# ── 物品图标 ───────────────────────────────────────────────────────
def test_detail_body_renders_item_icons():
    """说明与目标行中的 #c 物品码：有图标素材时按图标绘制，不抛错。"""
    import pygame

    from game.render.windows.core.services import WindowServices
    from tests.windows_harness import FakeAssets, FakeUI

    class IconAssets(FakeAssets):
        def item_icon(self, item_id: str):
            return pygame.Surface((12, 12), pygame.SRCALPHA)

    defs = {"q1": make_def("任务一", desc1="收集 #c4000004# 交给 #p90001#")}
    player = make_player(["q1"], defs)
    svc = WindowServices(assets=IconAssets(), ui=FakeUI(), player=lambda: player)
    svc.quest_goal_lines = lambda qid: ["收集 #c4000004# 0/5"]
    win = QuestLogWindow(svc)
    win.open()
    draw_once(make_manager(win))
    assert win.selected == "q1"


def test_detail_body_falls_back_without_icon_assets():
    """图标素材缺失（FakeAssets.item_icon None）时含 #c 码的说明照常绘制不抛错。"""
    defs = {"q1": make_def("任务一", desc1="收集 #c4000004#")}
    win, mgr = open_log(make_player(["q1"], defs))
    draw_once(mgr)
    assert win.selected == "q1"


def test_reward_view_lists_items_with_icons():
    """奖励视图条目带 #c 图标码，有/无图标素材均绘制不抛错。"""
    defs = {"q1": make_def("任务一")}
    defs["q1"].reward_items = [(4000004, 2)]
    win, mgr = open_log(make_player(["q1"], defs))
    win.show_reward = True
    draw_once(mgr)
    assert win.visible


# ── 详情区滚动 ─────────────────────────────────────────────────────
def test_detail_wheel_scrolls_when_overflow():
    """详情内容超一屏时，在详情区滚轮移动 win.detail_offset。"""
    defs = {"q1": make_def("任务一", desc1="很长的说明" * 200)}
    win, mgr = open_log(make_player(["q1"], defs))
    assert win.detail_offset == 0
    detail_pos = (win.rect.left + LIST_W + GAP + 100, win.rect.top + 200)
    assert wheel(mgr, detail_pos, up=False)
    assert win.detail_offset > 0


def test_detail_offset_resets_on_selection():
    """切换选中任务 / 页签 / 奖励视图时详情滚动位置归零。"""
    defs = {"q1": make_def("任务一", desc1="很长的说明" * 200),
            "q2": make_def("任务二")}
    win, mgr = open_log(make_player(["q1", "q2"], defs))
    detail_pos = (win.rect.left + LIST_W + GAP + 100, win.rect.top + 200)
    wheel(mgr, detail_pos, up=False)
    assert win.detail_offset > 0
    row_q2 = next(r for r, qid in win.row_rects if qid == "q2")
    press(mgr, row_q2.center)
    assert win.detail_offset == 0


# ── 静态目标行去重 ─────────────────────────────────────────────────
def test_strip_static_goal_lines_removes_item_objective_rows():
    """desc1 里官方自带的静态目标行（#t/#c 开头、/N 结尾）被剔除，正文保留。"""
    desc = ("剧情说明……\\n\\n"
            "#t4000011# #b#c4000011##k/10 \\n"
            "#t4000001# #b#c4000001##k/40")
    out = strip_static_goal_lines(desc)
    assert out.startswith("剧情说明")
    assert "#t4000011#" not in out and "/10" not in out and "/40" not in out


def test_strip_static_goal_lines_keeps_prose_with_macros():
    """正文中间引用物品宏的句子不会被误删。"""
    desc = "把#t4000011#交给#p9000320#。"
    assert strip_static_goal_lines(desc) == desc.replace("\\n", "\n")


def test_active_detail_drops_static_goals_when_dynamic_exist():
    """进行中页：有收集/击杀动态目标行时，desc1 里的重复静态行被剔除。"""
    defs = {"q1": make_def(
        "任务一",
        desc1="剧情……\\n\\n#t4000011# #b#c4000011##k/10")}
    defs["q1"].end_items = [(4000011, 10)]
    win, _ = open_log(make_player(["q1"], defs),
                      lambda qid: ["收集 #c4000011# 0/10"])
    body = win.detail_chunks("q1")
    assert any("0/10" in c for c in body)
    assert not any("#k/10" in c for c in body)


def test_active_detail_keeps_static_goals_without_dynamic_rows():
    """无动态目标行（如纯交对话任务）时，desc1 原样保留（静态行是唯一目标信息）。"""
    defs = {"q1": make_def(
        "任务一",
        desc1="剧情……\\n\\n#t4000011# #b#c4000011##k/10")}
    win, _ = open_log(make_player(["q1"], defs))
    body = win.detail_chunks("q1")
    assert any("#k/10" in c for c in body)


# ── chrome / 事件 / 锚点 ───────────────────────────────────────────
def test_close_button_click_closes_questlog():
    """点列表窗标题区关闭钮即关窗（经 manager 全链路）。"""
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
    """默认锚点右下（双联排总宽），底部为状态栏预留 BAR_RESERVE。"""
    win, mgr = open_log(make_player([], {}))
    assert win.rect.x == 800 - QUEST_WIN_W - 4
    assert win.rect.bottom == 600 - BAR_RESERVE - 2
