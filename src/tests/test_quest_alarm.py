"""可接任务列表（QuestAlarm）分页状态：条目切片、翻页、边界。"""
from __future__ import annotations

from game.render.quest_alarm import QuestAlarm, QuestEntry


def make_entry(i: int) -> QuestEntry:
    return QuestEntry(title=f"任务{i}", level=10 + i, tag="推荐", subtitle=f"Lv. {10 + i}")


def test_empty_has_single_blank_page():
    """空列表：只有一页、无可翻页，可见条目为空。"""
    m = QuestAlarm(entries=[])
    assert m.page_count == 1
    assert m.visible() == []
    assert m.can_next is False
    assert m.can_prev is False


def test_visible_slices_first_page():
    """条目不超一页时当前页完整显示。"""
    m = QuestAlarm(entries=[make_entry(i) for i in range(3)], per_page=5)
    assert m.visible() == [make_entry(i) for i in range(3)]


def test_page_count_rounds_up():
    """页数按每页条数向上取整。"""
    m = QuestAlarm(entries=[make_entry(i) for i in range(9)], per_page=4)
    assert m.page_count == 3


def test_next_page_advances_then_clamps():
    """next_page 成功前进，末页再调用返回 False 且不越界。"""
    m = QuestAlarm(entries=[make_entry(i) for i in range(9)], per_page=4)
    assert m.next_page() is True
    assert m.page == 1
    assert m.next_page() is True
    assert m.next_page() is False
    assert m.page == 2


def test_prev_page_returns_then_clamps():
    """prev_page 在非首页可回退，首页调用返回 False。"""
    m = QuestAlarm(entries=[make_entry(i) for i in range(9)], per_page=4)
    m.next_page()
    assert m.prev_page() is True
    assert m.page == 0
    assert m.prev_page() is False


def test_visible_returns_only_current_page():
    """翻页后可见条目只含当前页切片。"""
    entries = [make_entry(i) for i in range(9)]
    m = QuestAlarm(entries=entries, per_page=4)
    m.next_page()
    assert m.visible() == entries[4:8]
