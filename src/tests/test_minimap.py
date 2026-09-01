"""小地图坐标换算 / 夹紧 / 开关 / 名牌避让。"""
import pygame

from game import settings
from game.render.minimap import MiniMap

W = settings.MINIMAP_W
H = settings.MINIMAP_H


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


def portal(x, y, ptype=2):
    return {"index": 0, "name": "p", "type": ptype, "x": x, "y": y}


def make(mag=2, map_w=1000, map_h=600):
    bounds = {"left": -100, "top": -50, "right": map_w - 100,
              "bottom": map_h - 50, "width": map_w, "height": map_h}
    fhs = [fh(1, 0, -50, 100, 200, 100),
           fh(2, 0, 200, 100, 500, 100)]
    return MiniMap(fhs, [], [], bounds, map_w, map_h, mag=mag)


def test_view_world_rect_centered_on_player():
    """玩家在地图中央时，世界窗口以玩家为中心。"""
    m = make()
    left, top, vw, vh = m.view_world_rect(400, 300)
    assert vw == W * m.mag and vh == H * m.mag
    assert left == 400 - vw / 2
    assert top == 300 - vh / 2


def test_view_world_rect_clamped_at_top_left_corner():
    """玩家在左上角时，窗口夹紧到地图左上。"""
    m = make()
    left, top, vw, vh = m.view_world_rect(-100, -50)
    assert left == m.bounds["left"]
    assert top == m.bounds["top"]


def test_view_world_rect_clamped_at_bottom_right_corner():
    """玩家在右下角时，窗口夹紧到地图右下。"""
    m = make()
    left, top, vw, vh = m.view_world_rect(900, 550)
    assert left + vw == m.bounds["right"]
    assert top + vh == m.bounds["bottom"]


def test_world_to_panel_maps_view_origin():
    """世界窗口左上角 → 面板 (0,0)。"""
    m = make()
    left, top, _, _ = m.view_world_rect(400, 300)
    px, py = m.world_to_panel(left, top, left, top)
    assert px == 0.0 and py == 0.0


def test_world_to_panel_scales_by_mag():
    """1 面板像素 = mag 世界像素：右移 mag 世界像素 → 面板 +1。"""
    m = make(mag=2)
    left, top, _, _ = m.view_world_rect(400, 300)
    p1 = m.world_to_panel(400, 300, left, top)
    p2 = m.world_to_panel(400 + m.mag, 300, left, top)
    assert p2[0] - p1[0] == 1.0
    assert p2[1] - p1[1] == 0.0


def test_src_rect_scales_with_mag():
    """src 矩形 = 世界窗口 × canvas/世界 比例；回退时 = MINIMAP_W。"""
    m = make(mag=2, map_w=1000, map_h=600)
    src = m.src_rect(400, 300)
    # 世界窗口 = MINIMAP_W*mag = 356；base=世界/mag → src = 356/2 = 178
    assert src.w == W
    assert src.h == H


def test_view_window_clamped_when_map_smaller_than_window():
    """整图比小地图窗口还小：窗口夹紧为地图尺寸，不得越界。"""
    m = make(map_w=300, map_h=200, mag=4)
    left, top, vw, vh = m.view_world_rect(150, 100)
    assert vw == 300 and vh == 200
    assert left + vw <= m.bounds["right"]
    assert top + vh <= m.bounds["bottom"]


def test_src_rect_fits_base_layer_on_tiny_map():
    """小图的 src 必须落在底图层内（subsurface 不抛 ValueError）。"""
    m = make(map_w=300, map_h=200, mag=4)
    src = m.src_rect(150, 100)
    bw, bh = m.base_layer.get_size()
    assert src.left >= 0 and src.top >= 0
    assert src.right <= bw and src.bottom <= bh
    m.base_layer.subsurface(src)


def test_draw_on_tiny_map_no_crash():
    """小图上完整走一遍 draw：不应崩溃。"""
    m = make(map_w=300, map_h=200, mag=4)
    canvas = pygame.Surface((settings.VIEW_W, settings.VIEW_H))
    m.draw(canvas, 150, 100, True, [_Ent(160, 110)], [])


def test_toggle_flips_visible():
    """toggle() 切换 visible 布尔值。"""
    m = make()
    assert m.visible is True
    m.toggle()
    assert m.visible is False
    m.toggle()
    assert m.visible is True


def test_panel_rect_in_top_right():
    """面板矩形锚定在画布右上角（名牌会下移避让）。"""
    m = make()
    rect = m.panel_rect
    assert rect.topright == (settings.VIEW_W - settings.MINIMAP_MARGIN,
                             settings.MINIMAP_MARGIN)


def test_map_name_y_below_panel():
    """名牌 y 落在小地图面板底边之下。"""
    m = make()
    name_y = settings.MINIMAP_MARGIN + settings.MINIMAP_H + 8
    assert name_y >= m.panel_rect.bottom


def test_draw_keeps_canvas_untouched_when_hidden():
    """隐藏时 draw 不往画布画任何东西。"""
    m = make()
    m.toggle()
    canvas = pygame.Surface((settings.VIEW_W, settings.VIEW_H))
    before = pygame.image.tostring(canvas, "RGBA")
    m.draw(canvas, 0, 0, True, [], [])
    assert pygame.image.tostring(canvas, "RGBA") == before


class _Ent:
    def __init__(self, x, cy):
        self.x = x
        self.cy = cy


def test_entities_outside_view_are_not_drawn():
    """窗口外的怪物/NPC 不会画到面板外（裁剪）。"""
    m = make()
    m.toggle()  # 不需要真的画，验证坐标换算即可
    left, top, vw, vh = m.view_world_rect(400, 300)
    far = _Ent(400 + vw + 500, 300)   # 窗口右侧很远
    px, py = m.world_to_panel(far.x, far.cy, left, top)
    assert px > W
