"""状态栏 Key 按钮：热区登记、命中、三态贴图选择与按压动画。

全部走 UI 公开接口（draw_hud / key_button_hit / handle_mouse_event /
key_button_frame），素材用合成 assets 驱动，不依赖真实 WZ。
"""
from __future__ import annotations

import pygame

pygame.init()

from game.render.ui import UI, KEY_BUTTONS, KEY_BUTTON_WINDOWS

BTN_SIZE = (28, 28)
VIEW = (960, 540)


# ── 合成素材与假实体 ────────────────────────────────────────────────
class KeyBtnAssets:
    """任意 UI 路径一律返回空白贴图，并记录被请求的贴图路径。"""

    def __init__(self) -> None:
        self.requested: list = []

    def ui_surface(self, img: str, path: str):
        self.requested.append(path)
        return pygame.Surface(BTN_SIZE, pygame.SRCALPHA), (0, 0)


class _Inv:
    def total_items(self) -> int:
        return 0


class _Player:
    def __init__(self) -> None:
        self.hp = self.max_hp = 100
        self.mp = self.max_mp = 50
        self.exp = 0
        self.level = 1
        self.inventory = _Inv()

    def exp_to_next(self) -> int:
        return 100


class _Combat:
    total_kills = 0
    meso = 0


def make_ui() -> UI:
    return UI(KeyBtnAssets())


def draw_hud(ui: UI, mouse=None, left_down: bool = False) -> None:
    surface = pygame.Surface(VIEW, pygame.SRCALPHA)
    ui.draw_hud(surface, _Player(), _Combat(), mouse=mouse,
                left_down=left_down)


def down_event() -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (0, 0)})


def up_event() -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (0, 0)})


# ── 热区登记与命中 ──────────────────────────────────────────────────
def test_seven_key_buttons_registered_left_to_right():
    ui = make_ui()
    draw_hud(ui)
    names = [name for _, name in ui.key_buttons]
    assert names == list(KEY_BUTTONS)
    rects = [rect for rect, _ in ui.key_buttons]
    assert all(a.right <= b.x for a, b in zip(rects, rects[1:]))


def test_hotzone_hit_maps_to_button_name():
    ui = make_ui()
    draw_hud(ui)
    rect, name = ui.key_buttons[2]
    assert ui.key_button_hit(rect.center) == name
    assert ui.key_button_hit((5, 5)) is None


# ── 三态贴图选择 ────────────────────────────────────────────────────
def test_idle_uses_normal_frame():
    ui = make_ui()
    draw_hud(ui)
    name = KEY_BUTTONS[0]
    assert ui.key_button_frame(name, mouse=(-1, -1), left_down=False,
                               now=0) == f"{name}/normal/0"


def test_hover_uses_mouseover_frame():
    ui = make_ui()
    rect, name = _hovered_button(ui)
    assert ui.key_button_frame(name, mouse=rect.center, left_down=False,
                               now=0) == f"{name}/mouseOver/0"


def _hovered_button(ui: UI):
    draw_hud(ui)
    rect, name = ui.key_buttons[1]
    draw_hud(ui, mouse=rect.center)
    return rect, name


# ── 按钮 → 窗口映射 ────────────────────────────────────────────────
def test_key_buttons_map_to_windows():
    assert KEY_BUTTON_WINDOWS == {
        "EquipKey": "equip", "InvenKey": "inv", "StatKey": "stat",
        "SkillKey": "skill", "KeySet": "keyconfig",
    }


# ── 点击消费与按压动画 ──────────────────────────────────────────────
def test_click_outside_hotzone_not_consumed():
    ui = make_ui()
    draw_hud(ui)
    assert ui.handle_mouse_event(down_event(), (5, 5), now=1000) is None


def test_click_down_consumed_and_plays_press_animation():
    ui = make_ui()
    draw_hud(ui)
    rect, name = ui.key_buttons[3]
    assert ui.handle_mouse_event(down_event(), rect.center, now=1000) == name
    assert ui.key_button_frame(name, mouse=(-1, -1), left_down=True,
                               now=1000) == f"{name}/ani/0"
    assert ui.key_button_frame(name, mouse=(-1, -1), left_down=True,
                               now=1150) == f"{name}/ani/1"
    assert ui.key_button_frame(name, mouse=(-1, -1), left_down=True,
                               now=1300) == f"{name}/normal/0"


def test_held_after_animation_shows_pressed_until_release():
    ui = make_ui()
    draw_hud(ui)
    rect, name = ui.key_buttons[0]
    assert ui.handle_mouse_event(down_event(), rect.center, now=1000) == name
    assert ui.key_button_frame(name, mouse=rect.center, left_down=True,
                               now=1300) == f"{name}/pressed/0"
    assert ui.handle_mouse_event(up_event(), rect.center, now=1400) is None
    assert ui.key_button_frame(name, mouse=rect.center, left_down=False,
                               now=1500) == f"{name}/mouseOver/0"
