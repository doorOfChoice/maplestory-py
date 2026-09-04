"""技能窗滚动 / 页签 / 升级：经 WindowManager.dispatch 驱动 SkillWindow 公开接口。

继承旧 test_panels_scroll 技能部分意图：不满一屏不滚、滚轮按行滚、到底限幅、
窗口外不消费；另验证转数页签切换重置滚动、点升级按钮调用 skills.learn。
全走 fallback 自绘路径（FakeAssets 素材缺失 → ui_surface 恒 None），不依赖 WZ。
"""

from __future__ import annotations

from types import SimpleNamespace

from game.core.jobs import job_chain, job_sp_group
from game.render.windows.skill import SkillWindow
from tests.windows_harness import (draw_once, make_manager, make_services,
                                   press, wheel)


class FakeSkills:
    """最小技能书替身：只提供技能窗绘制/滚动/升级路径用到的公开接口。"""

    def __init__(self, n: int, job: int = 3000, sp: int = 0) -> None:
        self.job = job
        self.sp = sp
        self.learned: list = []
        self.defs = {f"s{i}": SimpleNamespace(id=f"s{i}", name=f"技{i}", desc="",
                                              max_level=1, char_level=1,
                                              invisible=False,
                                              stat=lambda lv, k, d=0: d)
                     for i in range(n)}
        self.levels = {}
        self.hotkeys = {}
        self.sp_by_job = {}

    @property
    def total_sp(self) -> int:
        return 0

    def sp_for_group(self, group: int) -> int:
        return self.sp

    def skills_for_group(self, group: int) -> list:
        return sorted(self.defs)

    def learnable(self, owner_group=None) -> list:
        return sorted(self.defs)

    def learn(self, skill_id: str, player_level: int) -> bool:
        self.learned.append((skill_id, player_level))
        return True


def make_player(n_skills: int = 0, job: int = 3000, sp: int = 0,
                level: int = 10) -> SimpleNamespace:
    return SimpleNamespace(skills=FakeSkills(n_skills, job=job, sp=sp),
                           level=level)


def open_window(player) -> tuple:
    """打开技能窗并完成首帧绘制（外框与热区就绪），返回 (manager, window)。"""
    win = SkillWindow(make_services(player))
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    return mgr, win


def test_skill_wheel_below_one_screen_consumed_but_stays():
    """技能不满一屏：滚轮被窗口消费，但滚动偏移保持 0。"""
    mgr, win = open_window(make_player(n_skills=3))
    assert wheel(mgr, win.rect.center, up=False)
    assert win._scroll.offset == 0


def test_skill_wheel_scrolls_by_one_row():
    """超过一屏后，滚轮每格按一行滚动，上滚可回退。"""
    mgr, win = open_window(make_player(n_skills=10))
    wheel(mgr, win.rect.center, up=False)
    assert win._scroll.offset == 1
    wheel(mgr, win.rect.center, up=False)
    assert win._scroll.offset == 2
    wheel(mgr, win.rect.center, up=True)
    assert win._scroll.offset == 1


def test_skill_wheel_clamps_at_bottom_and_top():
    """滚到末屏（10 技能 / fallback 一屏 7 行 → 偏移 3）与首屏后继续滚不越界。"""
    mgr, win = open_window(make_player(n_skills=10))
    for _ in range(20):
        wheel(mgr, win.rect.center, up=False)
    assert win._scroll.offset == 3
    for _ in range(20):
        wheel(mgr, win.rect.center, up=True)
    assert win._scroll.offset == 0


def test_skill_wheel_outside_window_not_consumed():
    """滚轮落在窗口外：不消费（穿透给世界），偏移不动。"""
    mgr, win = open_window(make_player(n_skills=10))
    assert not wheel(mgr, (5, 5), up=False)
    assert win._scroll.offset == 0


def test_skill_tab_click_switches_group_and_resets_scroll():
    """多转职业显示页签条；点旧转页签切换分组并把滚动归零。"""
    player = make_player(n_skills=10, job=3110)
    mgr, win = open_window(player)
    groups = [job_sp_group(jd.code) for jd in job_chain(player.skills.job)]
    assert len(win._tab_rects) == 4 and groups[-1] == 311   # 新手 + 三转
    wheel(mgr, win.rect.center, up=False)          # 先滚开一行
    tab_rect, grp = win._tab_rects[0]
    assert press(mgr, tab_rect.center)
    assert win._tab == grp and win._scroll.offset == 0


def test_learn_button_click_calls_learn_with_skill_and_level():
    """本转有 SP 时未学技能行尾出现升级按钮，点击调用 learn(sid, player.level)。"""
    player = make_player(n_skills=3, sp=2, level=21)
    mgr, win = open_window(player)
    assert win._row_rects
    rect, sid = win._row_rects[0]
    assert press(mgr, rect.center)
    assert player.skills.learned == [(sid, 21)]


def test_click_inside_blank_window_is_consumed():
    """点窗口内空白处：消费点击不穿透，也不触发学习。"""
    player = make_player(n_skills=3, sp=2, level=21)
    mgr, win = open_window(player)
    assert press(mgr, (win.rect.x + 4, win.rect.y + 30))
    assert player.skills.learned == []
