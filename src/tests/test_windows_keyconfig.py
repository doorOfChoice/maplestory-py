"""键盘式按键设置窗：上半虚拟键盘、下半指令栏，纯鼠标拖拽改绑。

透过 KeyConfigWindow + WindowManager 公开接口验证行为（不依赖 WZ 素材）：
指令拖到键格 = 改绑（冲突自动互换）并落盘；右键键格恢复默认；滚轮只翻指令
栏；Esc 键格只做展示、不是落点。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pygame

from game.core.keybindings import (ACTION_BY_ID, ACTIONS, GROUP_SKILL,
                                   KeyBindings)
from game.render.windows.keyconfig import KeyConfigWindow
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DragPickup
from tests.windows_harness import (FakeAssets, FakeUI, draw_once,
                                   make_manager, motion, press, release)


# ── 测试装配助手 ────────────────────────────────────────────────────
class FakeBindings:
    """记录改绑/重置/落盘调用的假绑定表；attack 恒显示占用 A 键。"""

    def __init__(self) -> None:
        self.set_calls: list = []
        self.reset_calls: list = []
        self.saved = 0

    def key_of(self, action: str) -> int:
        return pygame.K_a

    def action_for(self, key: int):
        return "attack" if key == pygame.K_a else None

    def slot_key(self, slot: int) -> int:
        return pygame.K_a

    def set(self, action: str, key: int) -> bool:
        self.set_calls.append((action, key))
        return True

    def reset(self, action: str) -> None:
        self.reset_calls.append(action)

    def save(self) -> None:
        self.saved += 1


def make_window(bindings=None, player=None) -> KeyConfigWindow:
    svc = WindowServices(assets=FakeAssets(), ui=FakeUI(),
                         player=lambda: player, bindings=bindings)
    return KeyConfigWindow(svc)


def make_open(bindings=None, player=None) -> tuple:
    """开窗 + 装配 manager + 画一帧登记键格与指令行。"""
    win = make_window(bindings, player)
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    return win, mgr


def row_center(win: KeyConfigWindow, action: str) -> tuple:
    return next(rect.center for rect, a in win.rows if a == action)


def cell_for(win: KeyConfigWindow, key: int) -> pygame.Rect:
    return next(rect for rect, k in win.key_cells if k == key)


def palette_actions() -> set:
    """指令栏应展示的全部动作（技能组除外——技能只从技能窗拖入）。"""
    return {a.id for a in ACTIONS if a.group != GROUP_SKILL}


def drag_to_key(mgr, win, action: str, key: int) -> None:
    assert press(mgr, row_center(win, action))
    target = cell_for(win, key)
    assert motion(mgr, target.center)
    assert release(mgr, target.center)


# ── 键盘绘制 ────────────────────────────────────────────────────────
def test_escaped_key_is_display_only():
    """Esc 画在键盘上但不进绑定落点表。"""
    win, _ = make_open(FakeBindings())
    assert pygame.K_ESCAPE not in [k for _, k in win.key_cells]
    assert cell_for(win, pygame.K_SPACE)          # 常规键都在


def test_palette_shows_all_actions_as_tiles():
    """方块网格一屏放得下全部指令（技能组不上栏），无需滚动。"""
    win, _ = make_open(FakeBindings())
    assert {a for _, a in win.rows} == palette_actions()


def test_palette_tiles_use_two_char_labels():
    """每个指令方块的文本都精简为恰好两个字。"""
    win, _ = make_open(FakeBindings())
    for _, action in win.rows:
        assert len(win.row_label(action)) == 2, action


# ── 拖拽改绑 ────────────────────────────────────────────────────────
def test_drag_command_row_onto_key_binds_and_saves():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    drag_to_key(mgr, win, "attack", pygame.K_j)
    assert fb.set_calls == [("attack", pygame.K_j)]
    assert fb.saved == 1


def test_drag_command_conflict_swaps_and_persists():
    """把「普通攻击」拖到拾取键 Z：攻击占 Z、拾取顶到 A，并写盘。"""
    kb = KeyBindings()
    with tempfile.TemporaryDirectory() as td:
        kb.path = Path(td) / "kb.json"
        win, mgr = make_open(kb)
        drag_to_key(mgr, win, "attack", pygame.K_z)
        assert kb.key_of("attack") == pygame.K_z
        assert kb.key_of("pickup") == pygame.K_a
        assert KeyBindings.load(kb.path).key_of("attack") == pygame.K_z


def test_drag_release_outside_keyboard_is_noop():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    assert press(mgr, row_center(win, "attack"))
    assert motion(mgr, (win.rect.right + 60, win.rect.centery))
    assert release(mgr, (win.rect.right + 60, win.rect.centery))
    assert fb.set_calls == []


def test_palette_pickup_produces_command_payload():
    win, _ = make_open(FakeBindings())
    rect = next(r for r, a in win.rows if a == "jump")
    pk = win.pickup(rect.center)
    assert pk is not None and pk.kind == "cmd"
    assert pk.payload == "jump" and pk.label == "跳跃"


# ── 右键恢复默认 ────────────────────────────────────────────────────
def test_right_click_bound_key_resets_chain_and_persists():
    """右键攻击现在所在的 J 键：攻击回 A，被顶去 A 的拾取链式回 Z。"""
    kb = KeyBindings()
    kb.set("attack", pygame.K_j)
    kb.set("pickup", pygame.K_a)
    with tempfile.TemporaryDirectory() as td:
        kb.path = Path(td) / "kb.json"
        win, mgr = make_open(kb)
        assert press(mgr, cell_for(win, pygame.K_j).center, button=3)
        assert kb.key_of("attack") == pygame.K_a
        assert kb.key_of("pickup") == pygame.K_z
        assert KeyBindings.load(kb.path).key_of("attack") == pygame.K_a


def test_right_click_free_key_does_nothing():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    press(mgr, cell_for(win, pygame.K_j).center, button=3)
    assert fb.reset_calls == []


# ── 技能落键（直接投递 handle_drop）────────────────────────────────
def make_player_book():
    from game.core.jobs import sp_group_of_skill
    from game.systems.skills import SkillBook, SkillDef
    sid = "3001000"
    book = SkillBook(assets=None, job=3000,
                     defs={sid: SkillDef(sid, "魔法箭", "",
                                         [{"damage": 100}], 5)})
    book.add_sp(sp_group_of_skill(sid), 3)
    book.learn(sid, 1)
    return SimpleNamespace(skills=book)


def test_drop_skill_onto_key_binds_its_slot():
    kb = KeyBindings()
    player = make_player_book()
    win, mgr = make_open(kb, player)
    pk = DragPickup(source=("skill", "3001000"), item=None,
                    home=win.rect, kind="skill", payload="3001000",
                    label="魔法箭")
    assert win.handle_drop(pk, cell_for(win, pygame.K_f).center)
    assert player.skills.hotkeys == {1: "3001000"}
    assert kb.key_of("skill_1") == pygame.K_f      # 顶掉的药水换到 1 键
    assert kb.key_of("potion") == pygame.K_1


def test_skill_keycap_text_uses_bound_skill_name():
    """键帽技能无图标时的文字回退：用槽位当前技能名，而非「技能 N」。"""
    player = SimpleNamespace(skills=SimpleNamespace(
        hotkeys={3: "9311005"},
        defs={"9311005": SimpleNamespace(name="断魂箭")}))
    win = make_window(FakeBindings(), player)
    assert win._action_text("skill_3") == "断魂箭"
    assert win._action_text("attack") == "攻击"


# ── 消耗品落键（背包拖入）──────────────────────────────────────────
def make_inventory_player():
    from game.systems.inventory import Inventory, Item
    inv = Inventory()
    inv.add(Item(id="2000000", name="红药", count=5, kind="consume",
                 info={"spec": {"hp": 50}}))
    inv.add(Item(id="1040013", name="短弓", count=1, kind="equip",
                 info={"islot": "SoSh"}))
    return SimpleNamespace(skills=None, inventory=inv)


def drop_item(win, mgr, player, item_id: str, key: int) -> bool:
    item = (player.inventory.consumes.get(item_id)
            or player.inventory.equips[0])
    pk = DragPickup(source=("cell", "consume", 0), item=item, home=win.rect)
    return win.handle_drop(pk, cell_for(win, key).center)


def test_drop_consume_onto_key_binds_item_action():
    """消耗品拖上键格：注册 item_<id> 动作并落盘，物品本身不被取出。"""
    kb = KeyBindings()
    player = make_inventory_player()
    with tempfile.TemporaryDirectory() as td:
        kb.path = Path(td) / "kb.json"
        win, mgr = make_open(kb, player)
        assert drop_item(win, mgr, player, "2000000", pygame.K_q)
        assert kb.key_of("item_2000000") == pygame.K_q
        assert player.inventory.consumes["2000000"].count == 5
        assert KeyBindings.load(kb.path).key_of("item_2000000") == pygame.K_q


def test_drop_non_consume_onto_key_rejected():
    kb = KeyBindings()
    player = make_inventory_player()
    win, mgr = make_open(kb, player)
    assert not drop_item(win, mgr, player, "1040013", pygame.K_q)
    assert "item_1040013" not in kb.keys


def test_item_keycap_text_uses_item_name():
    player = make_inventory_player()
    win = make_window(FakeBindings(), player)
    assert win._action_text("item_2000000") == "红药"


# ── 开合与图标绘制 ──────────────────────────────────────────────────
def test_toggle_flips_visibility():
    win = make_window(FakeBindings())
    assert not win.visible
    win.toggle()
    assert win.visible
    win.toggle()
    assert not win.visible


def test_bound_skill_key_and_tile_draw_with_icon():
    """技能有图标时：键帽与指令方块走图标分支，绘制不崩且热区完整。"""
    class IconAssets(FakeAssets):
        def skill_icon(self, skill_id: str):
            return pygame.Surface((20, 20))

    player = make_player_book()
    kb = KeyBindings()
    kb.set("skill_1", pygame.K_f)         # 1 号槽（魔法箭）落到 F 键
    svc = WindowServices(assets=IconAssets(), ui=FakeUI(),
                         player=lambda: player, bindings=kb)
    win = KeyConfigWindow(svc)
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    assert {a for _, a in win.rows} == palette_actions()
    assert cell_for(win, pygame.K_f)
