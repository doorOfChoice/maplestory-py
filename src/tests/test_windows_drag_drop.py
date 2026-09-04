"""背包 / 纸娃娃组件化窗口：拖出扔地、双击使用/穿戴/脱下、页签/滚轮/toggle。

全部经 WindowManager.dispatch 走真实事件链路；player 用真 Inventory +
SimpleNamespace 替身；热区来自真实 draw()（FakeAssets 素材缺失 → 全走
fallback 自绘路径，与官方底板行为等价）。
"""

from __future__ import annotations

from types import SimpleNamespace

from game.systems.inventory import Inventory, Item
from game.render.windows.inventory import (EquipWindow, InventoryWindow,
                                           toggle_inventory_pair)
from tests.windows_harness import (draw_once, make_manager, make_services,
                                   motion, press, release, wheel)


# ── 测试装配助手 ───────────────────────────────────────────────────
def make_player() -> SimpleNamespace:
    """最小玩家替身：真 Inventory + 计数 refresh_equips + 穿戴/恢复数值。"""
    refresh_calls: list = []
    return SimpleNamespace(
        inventory=Inventory(),
        refresh_equips=lambda: refresh_calls.append(1),
        refresh_calls=refresh_calls,
        level=10, hp=10, max_hp=50, mp=10, max_mp=50, job=0,
        total_stats=lambda: {"str": 20, "dex": 20, "int": 20, "luk": 20},
        attack_value=lambda: 10,
        defense_value=lambda: 10,
        skills=SimpleNamespace(total_sp=0),
    )


def build(player) -> tuple:
    """装配 svc（combat 带 10 万金币）+ 背包/纸娃娃两窗口 + manager。"""
    svc = make_services(player)
    svc.combat = SimpleNamespace(meso=100000)
    inv = InventoryWindow(svc)
    equip = EquipWindow(svc)
    mgr = make_manager(inv, equip)
    return mgr, inv, equip


def open_pair(mgr, inv, equip) -> None:
    """同开两窗并完成首帧绘制（登记热区）。"""
    inv.open()
    equip.open()
    draw_once(mgr)


def potion(item_id: str = "2000000", name: str = "红药",
           count: int = 12, hp: int = 50) -> Item:
    return Item(id=item_id, name=name, count=count, kind="consume",
                info={"spec": {"hp": hp}})


def shoe(req_level: int = 5) -> Item:
    return Item(id="1040013", name="蓝水鞋", kind="equip",
                info={"islot": "SoSh", "reqLevel": req_level, "incPDD": 3})


# ── ① ② 拖出扔地 / 拖回取消 ───────────────────────────────────────
def test_drag_out_of_inventory_home_drops_whole_stack():
    player = make_player()
    player.inventory.add(potion())
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    cell = inv._cell_rects[0][0]
    assert press(mgr, cell.center)
    assert motion(mgr, (720, 80))
    assert release(mgr, (720, 80))
    got = mgr.take_dropped()
    assert got is not None and got.id == "2000000" and got.count == 12
    assert player.inventory.consumes == {}
    assert mgr.take_dropped() is None       # 一次取走


def test_drag_out_and_back_into_home_cancels_drop():
    player = make_player()
    player.inventory.add(potion())
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    cell = inv._cell_rects[0][0]
    press(mgr, cell.center)
    motion(mgr, (720, 80))
    release(mgr, cell.center)               # 放回来源窗口
    assert mgr.take_dropped() is None
    assert player.inventory.consumes["2000000"].count == 12


# ── ③ ④ ⑤ 双击使用 / 穿戴 / 穿戴门控 ─────────────────────────────
def test_double_click_consume_heals_by_spec_and_decrements_count():
    player = make_player()
    player.inventory.add(potion())
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    cell = inv._cell_rects[0][0]
    for _ in range(2):                      # 双击 = 短间隔按下+松开 ×2
        press(mgr, cell.center)
        release(mgr, cell.center)
    assert player.hp == 50                  # 10 + 50 被 max_hp 截断
    assert player.inventory.consumes["2000000"].count == 11


def test_double_click_equip_cell_wears_and_refreshes():
    player = make_player()
    player.inventory.add(shoe())
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    inv.tab = "equip"
    draw_once(mgr)
    cell = inv._cell_rects[0][0]
    for _ in range(2):
        press(mgr, cell.center)
        release(mgr, cell.center)
    assert player.inventory.equipped.get("shoes") is not None
    assert player.inventory.equipped["shoes"].id == "1040013"
    assert len(player.refresh_calls) == 1


def test_double_click_equip_below_req_level_flashes_block():
    player = make_player()
    player.inventory.add(shoe(req_level=99))
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    inv.tab = "equip"
    draw_once(mgr)
    cell = inv._cell_rects[0][0]
    for _ in range(2):
        press(mgr, cell.center)
        release(mgr, cell.center)
    assert mgr._toast is not None and "无法穿戴" in mgr._toast[0]
    assert player.inventory.equipped == {}


# ── ⑥ 纸娃娃格拖出 = 脱下扔出 / 双击 = 脱下回背包 ─────────────────
def test_drag_equipped_off_paperdoll_returns_item_and_unequips():
    player = make_player()
    cap = Item(id="1002798", name="小红帽", kind="equip", info={"islot": "CpH1"})
    player.inventory.equipped["cap"] = cap
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    slot_rect = next(r for r, s in equip._slot_rects if s == "cap")
    assert press(mgr, slot_rect.center)
    assert motion(mgr, (720, 80))
    assert release(mgr, (720, 80))
    assert mgr.take_dropped() is cap
    assert player.inventory.equipped == {}
    assert len(player.refresh_calls) == 1   # 扔出路径也刷新外观


def test_double_click_paperdoll_slot_unequips_to_bag():
    player = make_player()
    cap = Item(id="1002798", name="小红帽", kind="equip", info={"islot": "CpH1"})
    player.inventory.equipped["cap"] = cap
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    slot_rect = next(r for r, s in equip._slot_rects if s == "cap")
    for _ in range(2):
        press(mgr, slot_rect.center)
        release(mgr, slot_rect.center)
    assert player.inventory.equipped == {}
    assert cap in player.inventory.equips
    assert len(player.refresh_calls) == 1


# ── ⑦ 页签切换命中 ─────────────────────────────────────────────────
def test_tab_click_switches_inventory_tab_and_cells():
    player = make_player()
    player.inventory.add(shoe())
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    tab_rect = next(r for r, key in inv._tab_rects if key == "equip")
    assert press(mgr, tab_rect.center)
    release(mgr, tab_rect.center)
    assert inv.tab == "equip"
    draw_once(mgr)
    assert inv._cell_rects[0][1] == "equip"


# ── ⑧ 滚轮按行滚动 / 限幅 ──────────────────────────────────────────
def test_wheel_scrolls_inventory_by_row_and_clamps():
    player = make_player()
    for i in range(40):
        player.inventory.add(potion(item_id=str(2000000 + i),
                                    name=f"药{i}", count=1))
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    pos = inv.rect.center
    for _ in range(5):                      # 下滚 5 格 × 每格一行(4 格)
        assert wheel(mgr, pos, up=False)
    draw_once(mgr)
    assert inv._cell_rects[0][2] == 16      # 限幅到 40−24 的首格
    for _ in range(8):                      # 上滚越界 → 夹回 0
        assert wheel(mgr, pos, up=True)
    draw_once(mgr)
    assert inv._cell_rects[0][2] == 0
    assert wheel(mgr, (760, 40), up=False) is False   # 窗口外穿透


# ── ⑨ 拖出期间第二按被屏蔽（不重复拾取）────────────────────────────
def test_second_press_during_pick_does_not_repickup():
    player = make_player()
    player.inventory.add(potion(count=5))
    player.inventory.add(potion(item_id="2000001", name="蓝药", count=7))
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    cell_a = inv._cell_rects[0][0]
    cell_b = inv._cell_rects[1][0]
    assert press(mgr, cell_a.center)        # 拾起 A
    assert press(mgr, cell_b.center)        # 拖拽中被吞，不改为拾 B
    motion(mgr, (720, 80))
    release(mgr, (720, 80))
    got = mgr.take_dropped()
    assert got is not None and got.id == "2000000"
    assert player.inventory.consumes["2000001"].count == 7


# ── toggle_inventory_pair：同开同关 + 关窗清拖拽 ────────────────────
def test_toggle_inventory_pair_opens_both_and_closing_cancels_drag():
    player = make_player()
    player.inventory.add(potion())
    mgr, inv, equip = build(player)
    assert not inv.visible and not equip.visible
    toggle_inventory_pair(mgr)
    assert inv.visible and equip.visible
    draw_once(mgr)
    press(mgr, inv._cell_rects[0][0].center)    # 拾起后不松手直接关窗
    toggle_inventory_pair(mgr)
    assert not inv.visible and not equip.visible
    release(mgr, (720, 80))                     # 进行中的拖拽已被取消
    assert mgr.take_dropped() is None
    assert player.inventory.consumes["2000000"].count == 12


# ── 卷轴双击：_apply_scroll 全量流程（combat.meso 结算）─────────────
def test_double_click_scroll_charges_meso_and_burns_tuc():
    player = make_player()
    weapon = Item(id="1302000", name="短弓", kind="equip",
                  info={"islot": "WpSi"}, tuc=3)
    player.inventory.equipped["weapon"] = weapon
    player.inventory.add(Item(id="02340000", name="武器攻击力卷轴 60%",
                              count=2, kind="consume", info={"spec": {}}))
    mgr, inv, equip = build(player)
    open_pair(mgr, inv, equip)
    cell = inv._cell_rects[0][0]
    for _ in range(2):
        press(mgr, cell.center)
        release(mgr, cell.center)
    assert player.inventory.consumes["02340000"].count == 1
    assert weapon.tuc == 2                      # 成功/失败都扣一次次数
    assert mgr._toast is not None and "强化" in mgr._toast[0]
    combat = mgr.svc.combat
    assert combat.meso == 100000 - (500 + 200 * player.level)   # 强化费结算
    assert len(player.refresh_calls) == 1
