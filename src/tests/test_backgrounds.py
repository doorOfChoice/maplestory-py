"""背景逐帧绘制：视差公式 / 平铺铺满视口 / 自动滚动 / 选帧 / front 分层。

复刻原版客户端背景语义：屏幕锚点 = (x, y) - 相机 × (100 + r) / 100；
type 1/3/4/6/7 横向平铺、2/3/5/6/7 纵向平铺（步长 cx/cy，0 取图宽/高），
平铺范围铺满视口；type 4-7 另加 rx/ry 随时间自动滚动。
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings
from game.render.backgrounds import BackLayer, draw_layers, layer_blits, tile_offsets

VIEW_W, VIEW_H = 960, 540


def make_layer(w: int = 64, h: int = 64, ox: int = 0, oy: int = 0,
               x: int = 0, y: int = 0, rx: int = 0, ry: int = 0,
               bg_type: int = 0, cx: int = 0, cy: int = 0,
               front: bool = False, frames=None) -> BackLayer:
    pygame.init()
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    if frames is None:
        frames = [(surf, (ox, oy), 100)]
    return BackLayer(x=x, y=y, rx=rx, ry=ry, bg_type=bg_type,
                     cx=cx, cy=cy, front=front, frames=frames)


def test_type0_drawn_once_at_anchor_minus_origin():
    """type 0 不平铺：只在锚点减 origin 处画一次。"""
    layer = make_layer(w=100, h=80, ox=30, oy=20, x=500, y=300)
    blits = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)
    assert len(blits) == 1
    assert blits[0][1:] == (470, 280)


def test_parallax_moves_background_slower_than_camera():
    """视差：rx=-5 时背景只随相机移动 95%（原版 (100+rx)/100 公式）。"""
    layer = make_layer(w=100, h=80, x=500, y=0, rx=-5)
    blits = layer_blits(layer, 1000.0, 0.0, VIEW_W, VIEW_H, 0.0)
    assert blits[0][1] == 500 - 950


def test_parallax_vertical_with_ry():
    """ry 同理作用于纵向。"""
    layer = make_layer(w=100, h=80, x=0, y=400, ry=-10)
    blits = layer_blits(layer, 0.0, 500.0, VIEW_W, VIEW_H, 0.0)
    assert blits[0][2] == 400 - 450


def test_type3_tiles_cover_whole_view_without_gaps():
    """type 3 双向平铺：拷贝无缝铺满整个视口（宽视口也不露底）。"""
    layer = make_layer(w=64, h=64, bg_type=3)
    blits = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)
    ux = sorted({b[1] for b in blits})
    uy = sorted({b[2] for b in blits})
    assert ux[0] <= 0 and ux[-1] + 64 >= VIEW_W
    assert uy[0] <= 0 and uy[-1] + 64 >= VIEW_H
    assert all(b - a == 64 for a, b in zip(ux, ux[1:]))
    assert all(b - a == 64 for a, b in zip(uy, uy[1:]))
    assert len(blits) == len(ux) * len(uy)


def test_type3_tiling_follows_camera():
    """相机移动后平铺仍铺满视口（拷贝壳随视差锚点移动）。"""
    layer = make_layer(w=64, h=64, bg_type=3)
    blits = layer_blits(layer, 333.0, 217.0, VIEW_W, VIEW_H, 0.0)
    ux = sorted({b[1] for b in blits})
    uy = sorted({b[2] for b in blits})
    assert ux[0] <= 0 and ux[-1] + 64 >= VIEW_W
    assert uy[0] <= 0 and uy[-1] + 64 >= VIEW_H


def test_type1_tiles_only_horizontally():
    """type 1 仅横向平铺：纵向只有一行。"""
    layer = make_layer(w=64, h=64, y=100, bg_type=1)
    blits = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)
    assert {b[2] for b in blits} == {100}
    assert len({b[1] for b in blits}) > 1


def test_type2_tiles_only_vertically():
    """type 2 仅纵向平铺：横向只有一列。"""
    layer = make_layer(w=64, h=64, x=100, bg_type=2)
    blits = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)
    assert {b[1] for b in blits} == {100}
    assert len({b[2] for b in blits}) > 1


def test_explicit_cx_step_overrides_image_width():
    """cx/cy 非 0 时以其为平铺步长（原版语义）。"""
    layer = make_layer(w=64, h=64, bg_type=1, cx=100)
    blits = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)
    ux = sorted({b[1] for b in blits})
    assert all(b - a == 100 for a, b in zip(ux, ux[1:]))


def test_type4_scrolls_over_time():
    """type 4 横向自动滚动：rx 作速度，2 秒滚 rx*2000/200 像素。"""
    layer = make_layer(w=64, h=64, bg_type=4, cx=10_000, rx=-5)
    at_0 = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)[0][1]
    at_2s = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 2000.0)[0][1]
    assert at_2s - at_0 == -50


def test_type5_scrolls_vertically():
    """type 5 纵向自动滚动。"""
    layer = make_layer(w=64, h=64, bg_type=5, cy=10_000, ry=4)
    at_0 = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)[0][2]
    at_2s = layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 2000.0)[0][2]
    assert at_2s - at_0 == 40


def test_frame_selected_by_delay():
    """ani 背景按 delay 选帧。"""
    pygame.init()
    a = pygame.Surface((8, 8), pygame.SRCALPHA)
    b = pygame.Surface((8, 8), pygame.SRCALPHA)
    layer = BackLayer(x=0, y=0, rx=0, ry=0, bg_type=0, cx=0, cy=0,
                      front=False, frames=[(a, (0, 0), 100), (b, (0, 0), 100)])
    assert layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 0.0)[0][0] is a
    assert layer_blits(layer, 0.0, 0.0, VIEW_W, VIEW_H, 150.0)[0][0] is b


def test_tile_offsets_empty_when_step_too_large_to_reach_view():
    """平铺步长过大、锚点又在视口外时不产生任何拷贝。"""
    assert tile_offsets(2000, 64, 100_000, 0, VIEW_W) == []


def test_draw_layers_splits_front_and_back():
    """draw_layers 按 front 标志分两层绘制，保持 WZ 顺序。"""
    pygame.init()
    target = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    red = pygame.Surface((8, 8), pygame.SRCALPHA)
    red.fill((255, 0, 0, 255))
    green = pygame.Surface((8, 8), pygame.SRCALPHA)
    green.fill((0, 255, 0, 255))
    back = BackLayer(10, 10, 0, 0, 0, 0, 0, False, [(red, (0, 0), 100)])
    front = BackLayer(20, 20, 0, 0, 0, 0, 0, True, [(green, (0, 0), 100)])
    draw_layers(target, [back, front], 0.0, 0.0, VIEW_W, VIEW_H, 0.0, front=False)
    assert target.get_at((10, 10)) == (255, 0, 0, 255)
    assert target.get_at((20, 20))[3] == 0
    draw_layers(target, [back, front], 0.0, 0.0, VIEW_W, VIEW_H, 0.0, front=True)
    assert target.get_at((20, 20)) == (0, 255, 0, 255)


needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Map.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_back_items_extracts_100010000_layers():
    """wzpy 公开 seam：back_items 返回 100010000 全部 back 项及解码帧。"""
    from wzpy.wz_file import WzFile
    from wzpy.map import MapRenderer
    wz = WzFile.open(str(settings.WZ_DIR / "Map.wz"), region=settings.REGION)
    renderer = MapRenderer(wz)
    items = renderer.back_items("100010000")
    assert len(items) == 6
    sky = items[0]
    assert sky["type"] == 3 and sky["front"] is False
    assert len(sky["frames"]) == 1
    img, origin, delay = sky["frames"][0]
    assert img.size == (256, 256) and delay > 0
    clouds = items[1]
    assert clouds["type"] == 4 and clouds["rx"] == -5
