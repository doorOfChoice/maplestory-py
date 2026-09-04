"""按键绑定模型：动作→物理键的改绑 / 冲突互换 / 反查 / 持久化。

透过 KeyBindings 公开接口验证行为，不依赖 pygame 显示（仅用键码常量）。
"""

import tempfile
from pathlib import Path

import pygame

from game.core.keybindings import (ACTIONS, ACTION_BY_ID, KeyBindings,
                                   display_key)


# ── 默认表 ──────────────────────────────────────────────────────────

def test_defaults_cover_actions_uniquely():
    """默认绑定覆盖全部动作，且除移动/技能区外键位不重复。"""
    kb = KeyBindings()
    assert set(kb.keys) == {a.id for a in ACTIONS}
    holders: dict = {}
    for act, kc in kb.keys.items():
        holders.setdefault(kc, []).append(act)
    dups = {kc: acts for kc, acts in holders.items() if len(acts) > 1}
    assert dups == {}


def test_archer_skill_slots_default_numbers():
    """技能槽 1~9 默认绑数字键 1~9。"""
    kb = KeyBindings()
    for slot in range(1, 10):
        assert kb.slot_key(slot) == getattr(pygame, f"K_{slot}")


# ── 改绑 / 冲突 ─────────────────────────────────────────────────────

def test_set_rebinds_action():
    kb = KeyBindings()
    assert kb.set("attack", pygame.K_j)
    assert kb.key_of("attack") == pygame.K_j
    assert kb.action_for(pygame.K_j) == "attack"
    assert kb.action_for(pygame.K_a) is None


def test_conflict_swaps_both_actions():
    """攻击改到 Z（拾取键）：拾取自动顶到攻击原来的 A。"""
    kb = KeyBindings()
    kb.set("attack", pygame.K_z)
    assert kb.key_of("attack") == pygame.K_z
    assert kb.key_of("pickup") == pygame.K_a


def test_escape_is_never_bindable():
    """Esc 固定为取消/关闭，不允许绑到任何动作。"""
    kb = KeyBindings()
    assert not kb.set("attack", pygame.K_ESCAPE)
    assert kb.key_of("attack") == pygame.K_a


def test_unknown_action_rejected():
    kb = KeyBindings()
    assert not kb.set("fly", pygame.K_j)


def test_bind_new_item_action_registers():
    """item_<id> 动态动作可直接注册并占键。"""
    kb = KeyBindings()
    assert kb.set("item_2000000", pygame.K_q)
    assert kb.key_of("item_2000000") == pygame.K_q
    assert kb.action_for(pygame.K_q) == "item_2000000"


def test_item_action_displaces_holder_to_unbound():
    """新物品宏顶掉 A 键上的攻击：攻击解绑为 -1 而不是抢别的键。"""
    kb = KeyBindings()
    kb.set("item_2000000", pygame.K_a)
    assert kb.key_of("item_2000000") == pygame.K_a
    assert kb.key_of("attack") == -1


def test_item_action_roundtrip_and_reset():
    """物品宏随配置持久化；reset 即删除绑定（右键键位恢复默认）。"""
    kb = KeyBindings()
    kb.set("item_2000000", pygame.K_q)
    kb2 = KeyBindings.from_dict(kb.to_dict())
    assert kb2.key_of("item_2000000") == pygame.K_q
    kb2.reset("item_2000000")
    assert "item_2000000" not in kb2.keys


def test_rebind_same_key_is_noop():
    kb = KeyBindings()
    assert kb.set("attack", pygame.K_a)
    assert kb.key_of("attack") == pygame.K_a


def test_numpad_enter_normalizes_to_enter():
    """小键盘 Enter 与主 Enter 视为同一键位（对话键）。"""
    kb = KeyBindings()
    kb.set("talk", pygame.K_KP_ENTER)
    assert kb.key_of("talk") == pygame.K_RETURN
    assert kb.action_for(pygame.K_KP_ENTER) == "talk"


def test_reset_restores_default_key():
    kb = KeyBindings()
    kb.set("jump", pygame.K_w)
    kb.reset("jump")
    assert kb.key_of("jump") == pygame.K_SPACE


def test_skill_slot_lookup():
    """槽位键双向可查：数字键与改绑后的任意键都能解析回槽位。"""
    kb = KeyBindings()
    assert kb.skill_slot_for(pygame.K_3) == 3
    kb.set("skill_3", pygame.K_F7)
    assert kb.skill_slot_for(pygame.K_F7) == 3
    assert kb.skill_slot_for(pygame.K_3) is None
    assert kb.skill_slot_for(pygame.K_a) is None


# ── 序列化 / 文件 ───────────────────────────────────────────────────

def test_dict_roundtrip_preserves_bindings():
    kb = KeyBindings()
    kb.set("attack", pygame.K_j)
    kb2 = KeyBindings.from_dict(kb.to_dict())
    assert kb2.key_of("attack") == pygame.K_j


def test_from_dict_ignores_unknown_and_bad_values():
    """旧配置多余动作、非法键码直接忽略，已知动作照常生效。"""
    kb = KeyBindings.from_dict({"keys": {
        "attack": pygame.K_j, "fly": 99999, "jump": "space"}})
    assert kb.key_of("attack") == pygame.K_j
    assert kb.key_of("jump") == pygame.K_SPACE


def test_from_dict_duplicate_key_resolves_by_swap():
    """配置里两个动作占同一键：后读者生效，先读者被顶到对方原键。"""
    kb = KeyBindings.from_dict({"keys": {
        "attack": pygame.K_z, "pickup": pygame.K_z}})
    assert kb.key_of("pickup") == pygame.K_z
    assert kb.key_of("attack") == pygame.K_a


def test_missing_file_loads_defaults():
    with tempfile.TemporaryDirectory() as td:
        kb = KeyBindings.load(Path(td) / "nope.json")
        assert kb.key_of("attack") == pygame.K_a


def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "keybindings.json"
        kb = KeyBindings()
        kb.set("attack", pygame.K_j)
        kb.save(path)
        kb2 = KeyBindings.load(path)
        assert kb2.key_of("attack") == pygame.K_j


def test_corrupt_file_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "keybindings.json"
        path.write_text("{not json", encoding="utf-8")
        kb = KeyBindings.load(path)
        assert kb.key_of("attack") == pygame.K_a


def test_instance_remembers_path_for_quicksave():
    """load() 记住路径后，save() 无参即写回原文件。"""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "kb.json"
        kb = KeyBindings.load(path)
        kb.set("attack", pygame.K_j)
        kb.save()
        assert KeyBindings.load(path).key_of("attack") == pygame.K_j


# ── 键名显示 ────────────────────────────────────────────────────────

def test_display_key_names():
    assert display_key(pygame.K_LEFT) == "←"
    assert display_key(pygame.K_SPACE) == "Space"
    assert display_key(pygame.K_RETURN) == "Enter"
    assert display_key(pygame.K_KP_ENTER) == "Enter"
    assert display_key(pygame.K_a) == "A"
    assert display_key(pygame.K_1) == "1"
    assert display_key(pygame.K_F5) == "F5"
    assert display_key(pygame.K_MINUS) == "-"


def test_action_metadata_complete():
    """每个动作都有中文标签与分组，供设置窗渲染。"""
    assert ACTION_BY_ID["attack"].label == "普通攻击"
    for a in ACTIONS:
        assert a.label and a.group
        assert a.default != 0
