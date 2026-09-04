"""自绘鼠标光标：状态优先级、动画取帧、热点计算与目录加载。"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image

pygame.init()
pygame.display.set_mode((100, 100))

from game.render.cursor import (CLICK, CLICK_RIGHT, DEFAULT, DRAG,
                                GameCursor, hotspot_of)


def _opaque_rect(x: int, y: int, w: int, h: int,
                 size: tuple[int, int] = (48, 48)) -> pygame.Surface:
    """生成指定不透明矩形区域的透明表面（热点可预期）。"""
    s = pygame.Surface(size, pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    s.fill((255, 255, 255, 255), pygame.Rect(x, y, w, h))
    return s


def test_dragging_state_beats_pressed_button():
    assert GameCursor.pick_state(True, True, False) == DRAG
    assert GameCursor.pick_state(False, True, False) == CLICK
    assert GameCursor.pick_state(False, False, True) == CLICK_RIGHT
    assert GameCursor.pick_state(False, False, False) == DEFAULT


def test_drag_animation_loops_over_frames():
    frames = [_opaque_rect(0, 0, 1, 1) for _ in range(5)]
    c = GameCursor({DRAG: frames}, frame_ms=90)
    c.update(DRAG, 0)
    assert c.current is frames[0]
    c.update(DRAG, 90)
    assert c.current is frames[1]
    c.update(DRAG, 90 * 4)
    assert c.current is frames[4]
    c.update(DRAG, 90 * 5)
    assert c.current is frames[0]


def test_two_frame_loop_wraps_around():
    a, b = _opaque_rect(0, 0, 1, 1), _opaque_rect(0, 0, 1, 1)
    c = GameCursor({DRAG: [a, b]}, frame_ms=90)
    c.update(DRAG, 0)
    c.update(DRAG, 90)
    assert c.current is b
    c.update(DRAG, 200)
    assert c.current is a


def test_hotspot_is_topmost_opaque_row_center():
    s = _opaque_rect(20, 10, 4, 30)
    assert hotspot_of(s) == (21, 10)


def test_draw_places_hotspot_at_mouse_pos():
    c = GameCursor({DEFAULT: [_opaque_rect(20, 10, 4, 30)]}, frame_ms=90)
    c.update(DEFAULT, 0)
    target = pygame.Surface((120, 120), pygame.SRCALPHA)
    c.draw(target, (100, 100))
    assert target.get_at((100, 100))[3] == 255
    assert target.get_at((99, 99))[3] == 0


def _write_png(path: str) -> None:
    im = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    im.putpixel((19, 14), (255, 255, 255, 255))
    im.save(path)


def test_from_dir_loads_all_four_states(tmp_path):
    names = ["point.png",
             *[f"grab-page-0{i}.png" for i in range(1, 6)],
             "point-click-page-01.png", "point-click-page-02.png",
             "point-click-right-page-01.png", "point-click-right-page-02.png"]
    for n in names:
        _write_png(str(tmp_path / n))
    c = GameCursor.from_dir(tmp_path)
    assert c is not None
    assert len(c.frames[DEFAULT]) == 1
    assert len(c.frames[DRAG]) == 5
    assert len(c.frames[CLICK]) == 2
    assert len(c.frames[CLICK_RIGHT]) == 2


def test_from_dir_missing_files_returns_none(tmp_path):
    assert GameCursor.from_dir(tmp_path) is None
