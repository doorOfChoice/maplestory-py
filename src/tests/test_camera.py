"""相机：center_on 把视口位置取整成整数像素，消除地图 blit 与实体绘制的 ±1px 抖动。"""

from game.core.camera import Camera


def make_camera():
    # 大图：玩家坐标不触发边界夹紧，便于观察取整行为
    return Camera(5000, 2000, bounds_left=0, bounds_top=0)


def test_center_on_snaps_to_integer():
    """center_on 用浮点玩家坐标算出的视口位置会被取整成像素。"""
    cam = make_camera()
    cam.center_on(2500.7, 1000.3)
    assert cam.x == 2020   # int(2500.7 - 480)
    assert cam.y == 676    # int(1000.3 - 540*0.6)
    assert cam.x == int(cam.x) and cam.y == int(cam.y)


def test_map_and_entity_share_integer_basis():
    """取整后：地图截取起点（int）与实体屏幕像素（int）对同一世界点一致。"""
    cam = make_camera()
    cam.center_on(2500.7, 1000.3)
    world_x = 2500.0
    map_px = int(world_x) - cam.img_x           # 地图：该列在屏幕上的像素
    entity_px = int(world_x - cam.x)            # 实体：same 世界点绘制像素
    assert map_px == entity_px
    assert cam.img_x == cam.x - cam.bounds_left


def test_float_camera_would_drift_units():
    """未取整的浮点相机，其地图截取起点与实体像素会相差相机的小数部分。"""
    cam = Camera(5000, 2000, bounds_left=0, bounds_top=0)
    # 模拟旧行为：不取整
    cam.x, cam.y = 2020.7, 676.3
    fr = cam.x - cam.x  # 保留占位，避免未用告警
    del fr
    # 地图用 int(相机)，实体用 float：两者落到同一世界点的像素不同
    world_x = 2500.0
    map_px = int(world_x) - int(cam.x)
    entity_px = int(world_x - cam.x)
    assert map_px != entity_px  # 这正是取整要消除的漂移


def test_clamped_corner_still_integer():
    """边界夹紧后相机坐标仍为整数。"""
    cam = make_camera()
    cam.center_on(0.3, 0.2)
    assert cam.x == 0 and cam.y == 0
    assert cam.x == int(cam.x)
