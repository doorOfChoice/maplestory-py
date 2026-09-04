"""按键绑定：动作 id → pygame 键码的可配置映射。

设计：游戏内一切可操作键都收敛为「动作」（move_left / attack / skill_3 …），
输入层按动作查询键码，配置层只存一张 action → keycode 表。
- 冲突策略：改绑时与占用者自动互换（冒险岛式）。
- Esc 固定为取消/关闭，永不参与绑定，防止把退出入口改丢。
- 小键盘 Enter 归一化为主 Enter（同一物理语义）。
- 全局持久化：save 目录下的 keybindings.json，与角色存档解耦；缺失/损坏回退默认。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pygame

# ── 动作定义 ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ActionDef:
    id: str
    label: str          # 按键设置窗里的中文名
    group: str          # 分组标题（移动 / 动作 / 界面 / 技能）
    default: int        # 默认 pygame 键码


GROUP_MOVE = "移动"
GROUP_ACT = "动作"
GROUP_UI = "界面"
GROUP_SKILL = "技能"

_SKILL_DEFAULTS = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
                   pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9,
                   pygame.K_0, pygame.K_MINUS, pygame.K_EQUALS]

ACTIONS: List[ActionDef] = [
    ActionDef("move_left", "左移", GROUP_MOVE, pygame.K_LEFT),
    ActionDef("move_right", "右移", GROUP_MOVE, pygame.K_RIGHT),
    ActionDef("move_up", "上（爬绳/传送门）", GROUP_MOVE, pygame.K_UP),
    ActionDef("move_down", "下（下跳平台）", GROUP_MOVE, pygame.K_DOWN),
    ActionDef("jump", "跳跃", GROUP_ACT, pygame.K_SPACE),
    ActionDef("attack", "普通攻击", GROUP_ACT, pygame.K_a),
    ActionDef("pickup", "拾取", GROUP_ACT, pygame.K_z),
    ActionDef("potion", "快捷药水", GROUP_ACT, pygame.K_f),
    ActionDef("talk", "对话", GROUP_ACT, pygame.K_RETURN),
    ActionDef("respawn", "原地复活", GROUP_ACT, pygame.K_r),
    ActionDef("window_inventory", "背包窗口", GROUP_UI, pygame.K_i),
    ActionDef("window_skill", "技能窗口", GROUP_UI, pygame.K_k),
    ActionDef("window_stat", "状态窗口", GROUP_UI, pygame.K_b),
    ActionDef("window_quest", "任务日志", GROUP_UI, pygame.K_q),
    ActionDef("minimap", "小地图开关", GROUP_UI, pygame.K_m),
    ActionDef("window_keyconfig", "按键设置", GROUP_UI, pygame.K_o),
] + [
    ActionDef(f"skill_{i + 1}", f"技能 {i + 1}", GROUP_SKILL, key)
    for i, key in enumerate(_SKILL_DEFAULTS)
]

ACTION_BY_ID: Dict[str, ActionDef] = {a.id: a for a in ACTIONS}
SKILL_SLOT_COUNT = len(_SKILL_DEFAULTS)

# 动态动作族：背包消耗品拖上键格时按需注册 item_<物品id>
ITEM_ACTION_PREFIX = "item_"


def item_action(item_id: str) -> str:
    return f"{ITEM_ACTION_PREFIX}{item_id}"


def item_id_of_action(action: str) -> Optional[str]:
    """动作 id → 物品 id；非物品动作返回 None。"""
    if action.startswith(ITEM_ACTION_PREFIX):
        return action[len(ITEM_ACTION_PREFIX):]
    return None


def _normalize(key: int) -> int:
    """小键盘 Enter 与主 Enter 视为同一键位。"""
    return pygame.K_RETURN if key == pygame.K_KP_ENTER else key


# ── 键名显示 ────────────────────────────────────────────────────────

_DISPLAY = {
    pygame.K_LEFT: "←", pygame.K_RIGHT: "→", pygame.K_UP: "↑",
    pygame.K_DOWN: "↓", pygame.K_SPACE: "Space", pygame.K_RETURN: "Enter",
    pygame.K_KP_ENTER: "Enter", pygame.K_TAB: "Tab", pygame.K_BACKSPACE: "退格",
    pygame.K_DELETE: "Del", pygame.K_INSERT: "Ins", pygame.K_HOME: "Home",
    pygame.K_END: "End", pygame.K_PAGEUP: "PgUp", pygame.K_PAGEDOWN: "PgDn",
    pygame.K_ESCAPE: "Esc", pygame.K_CAPSLOCK: "Caps",
    pygame.K_LSHIFT: "Shift", pygame.K_RSHIFT: "Shift",
    pygame.K_LCTRL: "Ctrl", pygame.K_RCTRL: "Ctrl",
    pygame.K_LALT: "Alt", pygame.K_RALT: "Alt",
    pygame.K_MINUS: "-", pygame.K_EQUALS: "=", pygame.K_LEFTBRACKET: "[",
    pygame.K_RIGHTBRACKET: "]", pygame.K_BACKSLASH: "\\", pygame.K_SEMICOLON: ";",
    pygame.K_QUOTE: "'", pygame.K_COMMA: ",", pygame.K_PERIOD: ".",
    pygame.K_SLASH: "/", pygame.K_BACKQUOTE: "`",
}


def display_key(key: int) -> str:
    """键码 → 设置窗里显示的短名。"""
    if key in _DISPLAY:
        return _DISPLAY[key]
    if pygame.K_KP0 <= key <= pygame.K_KP9:
        return f"小键盘{key - pygame.K_KP0}"
    name = pygame.key.name(key)
    return name.upper() or "?"


# ── 绑定表 ──────────────────────────────────────────────────────────


class KeyBindings:
    """action → keycode 全表。set 即改绑（冲突自动互换），并支持文件持久化。"""

    __slots__ = ("keys", "path")

    def __init__(self, keys: Optional[Dict[str, int]] = None):
        self.keys: Dict[str, int] = dict(keys) if keys is not None \
            else {a.id: a.default for a in ACTIONS}
        self.path: Optional[Path] = None

    # ── 查询 ───────────────────────────────────────────────────────
    def key_of(self, action: str) -> Optional[int]:
        return self.keys.get(action)

    def action_for(self, key: int) -> Optional[str]:
        key = _normalize(key)
        return next((a for a, k in self.keys.items() if k == key), None)

    def slot_key(self, slot: int) -> Optional[int]:
        return self.keys.get(f"skill_{slot}")

    def skill_slot_for(self, key: int) -> Optional[int]:
        act = self.action_for(key)
        if act is not None and act.startswith("skill_"):
            return int(act[len("skill_"):])
        return None

    # ── 改绑 ───────────────────────────────────────────────────────
    def set(self, action: str, key: int) -> bool:
        """把 action 绑到 key。Esc 与非 item_ 的未知动作拒绝；占用者互换到该动作原键。

        新注册的 item_ 动作没有原键（-1），被它顶掉的占用者即告解绑。
        """
        if key == pygame.K_ESCAPE:
            return False
        if action not in self.keys:
            if not action.startswith(ITEM_ACTION_PREFIX):
                return False
            self.keys[action] = -1
        key = _normalize(key)
        old = self.keys[action]
        if old == key:
            return True
        holder = self.action_for(key)
        self.keys[action] = key
        if holder is not None:
            self.keys[holder] = old
        return True

    def reset(self, action: str, _seen: Optional[set] = None) -> None:
        """恢复默认键：默认键若被别的动作占用，递归把占用者也送回各自默认。

        动态 item_ 动作没有默认键，reset 即删除绑定（解绑）。
        """
        d = ACTION_BY_ID.get(action)
        if d is None:
            if action.startswith(ITEM_ACTION_PREFIX):
                self.keys.pop(action, None)
            return
        seen = _seen if _seen is not None else set()
        if action in seen:
            return
        seen.add(action)
        self.keys[action] = -1          # 暂时腾空，避免占用者查询撞到自己
        holder = self.action_for(d.default)
        if holder is not None:
            self.reset(holder, seen)
        self.keys[action] = d.default

    # ── 序列化 ─────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"version": 1, "keys": dict(self.keys)}

    @classmethod
    def from_dict(cls, data: dict) -> "KeyBindings":
        kb = cls()
        entries = (data or {}).get("keys")
        if isinstance(entries, dict):
            for action, key in entries.items():
                if isinstance(key, int):
                    kb.set(str(action), key)
        return kb

    @classmethod
    def load(cls, path: Path) -> "KeyBindings":
        """读文件；缺失/损坏回退默认。实例记住路径供无参 save() 用。"""
        try:
            kb = cls.from_dict(json.loads(Path(path).read_text("utf-8")))
        except (OSError, ValueError):
            kb = cls()
        kb.path = Path(path)
        return kb

    def save(self, path: Optional[Path] = None) -> None:
        target = Path(path) if path is not None else self.path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False,
                                     indent=1), encoding="utf-8")
        self.path = target
