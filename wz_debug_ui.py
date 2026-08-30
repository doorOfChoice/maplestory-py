#!/usr/bin/env python3
"""PySide6 纸娃娃调试器 + 可玩角色场景 for MapleStory Character.wz.

双模式切换(顶部工具栏)：
  · 游戏模式 —— 纸娃娃选好的装备实时渲染为可操控角色：方向键左右移动、
    空格/↑ 跳跃、J 攻击、R 复位。带重力、地面与左右边界。
  · 调试模式 —— 保留部位分层、悬浮明细、锚点/bbox 标注、保存 PNG 等原约束。
    底部共享同一拼接管线(_build_placements 与 compose_animation)。

左侧「纸娃娃 · 装备选择」按槽位(Body/Head/Hair/Face/Coat/Pants/Shoes/Weapon)
浏览装备缩略图(懒解码), 点击即换装并实时刷新；上方输入框可直接填装备 ID，
筛选框按 ID 过滤。

底层复用 ``wzpy.character.CharacterRenderer``：游戏模式用 ``compose_animation``
把每个姿态的帧预渲染成统一画布(锚定 navel)的 QPixmap，再用
``pose_frame_delays`` 驱动动画时序；调试模式复用 ``_build_placements``。

Usage:
    (cd tools && uv run wz_debug_ui.py)
"""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, QSize, QAbstractListModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import (
    QColor, QImage, QPixmap, QPainter, QPen, QBrush, QFont, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLineEdit, QCheckBox, QComboBox, QLabel,
    QPushButton, QGroupBox, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsSimpleTextItem, QGraphicsItem, QFileDialog, QHeaderView,
    QListView, QStackedWidget, QStyledItemDelegate,
)

import numpy as np
from PIL import Image

from wzpy.wz_file import WzFile
from wzpy.canvas import decode_canvas
from wzpy.character import (
    CharacterRenderer, DEFAULT_EAR_TYPE, SUPPORTED_POSES, CATEGORY_DIR,
    category_for_id, _determine_anchor,
)

WZ_PATH = os.environ.get("WZ_PATH", "./113/Character.wz")
REGION = "EMS"

# 槽位顺序与默认装备(含 Head 修复)
SLOTS = [
    ("Body",   "00002000"),
    ("Head",   "00012000"),
    ("Hair",   "00030000"),
    ("Face",   "00020000"),
    ("Coat",   "01040000"),
    ("Pants",  "01060000"),
    ("Shoes",  "01070000"),
    ("Weapon", "01302000"),
]

# 面板中每个槽位对应的 list_parts category(SLOTS 名 -> category)
SLOT_CATEGORY = {
    "Body": "Body", "Head": "Head", "Hair": "Hair", "Face": "Face",
    "Coat": "Coat", "Pants": "Pants", "Shoes": "Shoes", "Weapon": "Weapon",
}

CATEGORY_COLORS = {
    "Body":     QColor("#e6194b"),
    "Head":     QColor("#3cb44b"),
    "Hair":     QColor("#4363d8"),
    "Face":     QColor("#f58231"),
    "Cap":      QColor("#ffe119"),
    "Coat":     QColor("#911eb4"),
    "Longcoat": QColor("#f032e6"),
    "Pants":    QColor("#46f0f0"),
    "Shoes":    QColor("#bcf60c"),
    "Glove":    QColor("#fabebe"),
    "Cape":     QColor("#008080"),
    "Shield":   QColor("#e6beff"),
    "Weapon":   QColor("#9a6324"),
    "Effect":   QColor("#808080"),
}

ANCHOR_COLORS = {
    "navel":     QColor("#ffffff"),
    "neck":      QColor("#00ffff"),
    "brow":      QColor("#ffff00"),
    "hand":      QColor("#ff7f50"),
    "handMove":  QColor("#ff1493"),
    "lHand":     QColor("#ff7f50"),
    "earOverHead": QColor("#adff2f"),
    "earBelowHead": QColor("#adff2f"),
}

# 游戏物理参数
GRAVITY = 2200.0
MOVE_SPEED = 220.0
JUMP_VELOCITY = -760.0
GROUND_Y = 0            # 世界 navel 对齐的地面高度(x, y 网格用)
WORLD_BOUND_X = 900.0    # 半宽，左右边界

# 动画姿态(游戏模式状态机 -> pose)
POSE_IDLE = "stand1"
POSE_RUN = "walk1"
POSE_JUMP = "jump"
POSE_ATTACK = "swingO1"   # 无武器/不可用时回退到武器首个可用攻击姿态


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def canvas_node_to_pixmap(node) -> QPixmap:
    try:
        dec = decode_canvas(node)
    except Exception:
        pix = QPixmap(32, 32)
        pix.fill(QColor("#333333"))
        return pix
    return pil_to_pixmap(dec)


# ══════════════════════════════════════════════════════════════════════
# 装备缩略图模型 —— 懒解码
# ══════════════════════════════════════════════════════════════════════
class EquipListModel(QAbstractListModel):
    """按需枚举 list_parts(category) 的装备, 图标懒解码并缓存。"""

    def __init__(self, renderer, wz, category, parent=None):
        super().__init__(parent)
        self.renderer = renderer
        self.wz = wz
        self.category = category
        self._parts = []
        self._icons = {}
        self._meta = {}
        self._load()

    def _load(self):
        try:
            self._parts = self.renderer.list_parts(self.category)
        except Exception:
            self._parts = []
        self.beginResetModel()
        self._icons = {}
        self.endResetModel()

    # 图标路径解析(与 renderer.list_parts 的 icon_paths 约定一致)
    def _resolve_icon_node(self, equip_id, icon_paths):
        sub = CATEGORY_DIR.get(self.category, "")
        img = self.renderer._open_part(equip_id)
        if img is None:
            return None
        try:
            root = img.parse()
        except Exception:
            return None
        def walk(path):
            n = root
            for s in path.split("/"):
                n = n.child(s) if n else None
                if n is None:
                    return None
            return n
        for ip in icon_paths:
            # icon_paths 是 WZ-relative,含 sub 前缀; 拆成 path 段
            seg = ip.split("/")
            # 去掉 "Category/xxxx.img" 前两段
            path = "/".join(seg[2:]) if len(seg) >= 3 else ip
            node = walk(path)
            if node is not None:
                return node
        return None

    def _icon_for(self, row):
        if row in self._icons:
            return self._icons[row]
        p = self._parts[row]
        node = self._resolve_icon_node(p["id"], p.get("icon_paths", []))
        pix = canvas_node_to_pixmap(node) if node is not None else self._empty_pix()
        self._icons[row] = pix
        return pix

    @staticmethod
    def _empty_pix():
        pix = QPixmap(32, 32)
        pix.fill(QColor("#333333"))
        return pix

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._parts)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        p = self._parts[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{p['id']}"
        if role == Qt.ItemDataRole.ToolTipRole:
            sub = CATEGORY_DIR.get(self.category, "")
            names = p.get("names")
            return f"{p['id']}\n{sub}/{p['id']}.img"
        if role == Qt.ItemDataRole.DecorationRole:
            return self._icon_for(row)
        if role == Qt.ItemDataRole.UserRole:
            return p["id"]
        return None

    def part_id(self, row):
        if 0 <= row < len(self._parts):
            return self._parts[row]["id"]
        return None

    def find_id(self, equip_id):
        for i, p in enumerate(self._parts):
            if p["id"] == equip_id:
                return i
        return -1


class EquipListItemDelegate(QStyledItemDelegate):
    """限制缩略图尺寸并优化绘制。"""

    def sizeHint(self, option, index):
        return QSize(64, 40)


# ══════════════════════════════════════════════════════════════════════
# 动画帧缓存 —— 每个姿态的 QPixmap 帧列表
# ══════════════════════════════════════════════════════════════════════
class AnimCache:
    """pre-render 姿态帧 -> (QPixmap帧, delay_ms) 列表, 换装时失效。"""

    def __init__(self, renderer):
        self.renderer = renderer
        self.key = None
        self._poses = {}      # pose -> list[(QPixmap, delay_ms)]
        self._pose_delays = {}
        self.equips = ()

    def invalidate(self):
        self.key = None
        self._poses.clear()
        self._pose_delays.clear()

    # 先算出合成后 navel 在图内的像素位置，用于世界坐标对齐
    def render_pose(self, pose, equip_ids, ear_type, flip):
        key = (tuple(equip_ids), ear_type, flip, pose)
        hit = self._poses.get(key)
        if hit is not None:
            return hit

        frames_pil = self.renderer.compose_animation(
            list(equip_ids), pose, ear_type=ear_type, flip=flip,
        )
        delays = self.renderer.pose_frame_delays(pose, "00002000") or [100] * len(frames_pil)
        # 计算 navel 在图内像素坐标: 用 _build_placements 采样首帧世界锚点差异
        hide_full, hide_set, cap_vslot = self.renderer._cap_hair_filter(list(equip_ids))
        pls, anchors = self.renderer._build_placements(
            list(equip_ids), pose, ear_type, hide_full, hide_set, cap_vslot, 0,
            return_anchors=True,
        )
        # 世界 navel=(0,0). bbox 由 compose_animation 统一; 但我们需要图像内 navel 像素。
        # 简化: build_placements 给出各 part 的 top_left, 我们合成时以 navel(0,0) 为原点。
        # 需要知道合成图相对 navel 的 offsets -> 借助首帧渲染尺寸与内容紧包 bbox 偏差不大,
        # 故直接用 compose_animation 返回值 + 手工偏移: navel 在 “整个姿态所有帧紧包框” 的
        # (0-min_x, 0-min_y). 这里我们改用一个稳定的像素: 帧图的几何中心偏差较大，
        # 因此改为计算所有帧的紧包 bbox。
        navel_px = _animation_navel_px(
            self.renderer, equip_ids, pose, ear_type, flip, len(frames_pil),
        )
        frames = [(pil_to_pixmap(f), delays[min(i, len(delays) - 1)]) for i, f in enumerate(frames_pil)]
        result = (frames, navel_px)
        self._poses[key] = result
        self.equips = tuple(equip_ids)
        return result

    def clear_for(self, equip_ids):
        self._poses.clear()


def _animation_navel_px(renderer, equip_ids, pose, ear_type, flip, n_frames):
    """计算 compose_animation 输出帧内 navel 的像素坐标。

    compose_animation 把所有帧合成到“统一紧包 bbox”且 navel(世界 0,0)落在同一像素。
    这里用 _build_placements 遍历各帧的 top_left, 复刻 compose_animation 的 bbox 逻辑。
    """
    hide_full, hide_set, cap_vslot = renderer._cap_hair_filter(list(equip_ids))
    def w(p): return p.width_override if p.width_override is not None else p.pixel_canvas.width
    def h(p): return p.height_override if p.height_override is not None else p.pixel_canvas.height
    min_x = min_y = max_x = max_y = None
    for f in range(n_frames):
        pls, _ = renderer._build_placements(
            list(equip_ids), pose, ear_type, hide_full, hide_set, cap_vslot, f,
            return_anchors=True,
        )
        for p in pls:
            if p.top_left is None:
                continue
            x0, y0 = p.top_left
            x1, y1 = x0 + w(p), y0 + h(p)
            if min_x is None:
                min_x, min_y, max_x, max_y = x0, y0, x1, y1
            else:
                min_x = min(min_x, x0); min_y = min(min_y, y0)
                max_x = max(max_x, x1); max_y = max(max_y, y1)
    if min_x is None:
        return (0, 0)
    # navel 世界 (0,0). flip 时 x 镜像: 图像宽 W = max_x-min_x, navel 像素 = (0-min_x, 0-min_y)。
    npx = (0 - min_x, 0 - min_y)
    if flip:
        W = max(max_x - min_x, 1)
        npx = (W - 1 - npx[0], npx[1])
    return npx


# ══════════════════════════════════════════════════════════════════════
# 游戏场景视图 —— 带物理循环
# ══════════════════════════════════════════════════════════════════════
class GameView(QGraphicsView):
    """可玩法角色场景：重力、地面、左右边界、跳跃、攻击。"""

    def __init__(self, scene, app):
        super().__init__(scene)
        self.app = app
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._min_scale, self._max_scale = 0.5, 32.0

        # 角色状态
        self.sprite = QGraphicsPixmapItem()
        self.sprite.setZValue(10)
        scene.addItem(self.sprite)
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.facing_right = True
        self.attacking = False
        self.attack_pose = POSE_ATTACK

        self.pose = POSE_IDLE
        self.frame_index = 0
        self.frame_accum = 0.0

        # 当前动画缓存结果
        self._frames = []
        self._navel_px = (0, 0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000 // 30)

        # 键盘操控必须落在本视图: QGraphicsView 会截获方向键用于滚动,
        # 若放在主窗口则永远收不到。故在此强焦点并接管按键。
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    # ── 键盘输入(游戏模式) ──────────────────────────────────────────
    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Left:
            self.move_left()
        elif k == Qt.Key.Key_Right:
            self.move_right()
        elif k in (Qt.Key.Key_Space, Qt.Key.Key_Up):
            self.jump()
        elif k == Qt.Key.Key_J:
            self.attack()
        elif k == Qt.Key.Key_R:
            self.reset_character()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        k = event.key()
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.stop_move()
        else:
            super().keyReleaseEvent(event)

    # ── 画布绘制 ──────────────────────────────────────────────────────
    def _draw_world(self):
        scene = self.scene()
        # 移除旧的 world 标记(保留 sprite)
        for it in list(getattr(self, "_world_items", [])):
            if it.scene() is scene:
                scene.removeItem(it)
        self._world_items = []
        pen = QPen(QColor(255, 255, 255, 60), 0)
        self._world_items.append(
            scene.addLine(-WORLD_BOUND_X, 0, WORLD_BOUND_X, 0, QPen(QColor("#33aaee"), 2)))
        for g in range(-int(WORLD_BOUND_X), int(WORLD_BOUND_X) + 1, 40):
            if g == 0:
                continue
            self._world_items.append(scene.addLine(g, -16, g, 16, pen))
        self._world_items.append(
            scene.addLine(-WORLD_BOUND_X, -40, -WORLD_BOUND_X, 16, QPen(QColor("#aa3333"), 2)))
        self._world_items.append(
            scene.addLine(WORLD_BOUND_X, -40, WORLD_BOUND_X, 16, QPen(QColor("#aa3333"), 2)))
        # 确保 sprite 在场景顶层
        if self.sprite.scene() is not scene:
            scene.addItem(self.sprite)

    def _ensure_anim(self):
        """确保角色姿态的第一帧已预渲染。"""
        frames, navel = self._emit_anim(self.pose)
        self._frames = frames
        self._navel_px = navel
        self._apply_frame()

    def _emit_anim(self, pose):
        anim = self.app.anim_cache.render_pose(
            pose, self.app.equips(), self.app.ear_type, self.facing_right,
        )
        return anim

    def _apply_frame(self):
        if not self._frames:
            return
        idx = self.frame_index % len(self._frames)
        pix = self._frames[idx][0]
        self.sprite.setPixmap(pix)
        npx = self._navel_px
        # 精灵定位: 图像 navel 像素对齐世界 (x, y)
        self.sprite.setPos(self.x - npx[0], self.y - npx[1])

    def _tick(self):
        dt = 0.033
        # 物理
        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        self.x += self.vx * dt
        # 地面碰撞: y 回到地面 -> 着地
        if self.y >= GROUND_Y:
            self.y = GROUND_Y
            self.vy = 0.0
            self.on_ground = True
        else:
            self.on_ground = False
        # 左右边界
        if self.x < -WORLD_BOUND_X:
            self.x = -WORLD_BOUND_X; self.vx = 0
        if self.x > WORLD_BOUND_X:
            self.x = WORLD_BOUND_X; self.vx = 0

        # 状态机 -> pose
        if self.attacking:
            new_pose = self.attack_pose
        elif not self.on_ground:
            new_pose = POSE_JUMP
        elif abs(self.vx) > 1:
            new_pose = POSE_RUN
        else:
            new_pose = POSE_IDLE

        if new_pose != self.pose:
            self.pose = new_pose
            self.frame_index = 0
            self.frame_accum = 0.0
            frames, navel = self._emit_anim(self.pose)
            self._frames = frames
            self._navel_px = navel

        # 推进动画帧
        if self._frames:
            delay = self._frames[self.frame_index][1]
            self.frame_accum += dt * 1000.0
            if self.frame_accum >= delay:
                self.frame_accum -= delay
                self.frame_index = (self.frame_index + 1) % len(self._frames)
                # 非循环姿态(攻击/跳跃)播完后回到 idle
                if self.pose in (POSE_ATTACK, POSE_JUMP) and self.frame_index == 0:
                    if self.pose == POSE_ATTACK:
                        self.attacking = False

        self._apply_frame()
        self.centerOn(self.x, self.y)
        self.app.statusBar().showMessage(
            f"x={self.x:.0f} y={self.y:.0f} pose={self.pose} on_ground={self.on_ground}",
            500,
        )

    # ── 输入控制(由主窗口转发按键) ──────────────────────────────────
    def move_left(self):
        self.vx = -MOVE_SPEED
        self.facing_right = False

    def move_right(self):
        self.vx = MOVE_SPEED
        self.facing_right = True

    def stop_move(self):
        self.vx = 0.0

    def jump(self):
        if self.on_ground:
            self.vy = JUMP_VELOCITY
            self.on_ground = False

    def attack(self):
        if self.attacking:
            return
        self.attacking = True
        self.attack_pose = self.app.pick_attack_pose()
        self.frame_index = 0
        self.frame_accum = 0.0

    def reset_character(self):
        self.x = 0.0; self.y = GROUND_Y
        self.vx = 0.0; self.vy = 0.0
        self.on_ground = True
        self.attacking = False
        self.pose = POSE_IDLE
        self.frame_index = 0
        self.frame_accum = 0.0

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        target = self.transform().m11() * factor
        if self._min_scale <= target <= self._max_scale:
            self.scale(factor, factor)


# ══════════════════════════════════════════════════════════════════════
# 调试视图 —— 沿用原 DebugView 的缩放/拖拽/悬浮
# ══════════════════════════════════════════════════════════════════════
class DebugView(QGraphicsView):
    def __init__(self, scene, on_hover=None):
        super().__init__(scene)
        self.on_hover = on_hover
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._min_scale, self._max_scale = 0.5, 32.0

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        target = self.transform().m11() * factor
        if self._min_scale <= target <= self._max_scale:
            self.scale(factor, factor)

    def fit(self):
        if not self.scene().items():
            return
        self.fitInView(self.scene().itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.on_hover:
            item = self.itemAt(event.position().toPoint())
            placement = getattr(item, "placement", None)
            self.on_hover(placement)


# ══════════════════════════════════════════════════════════════════════
# 主窗口
# ══════════════════════════════════════════════════════════════════════
class DebugApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Character.wz 纸娃娃调试器")
        self.resize(1440, 900)

        self.wz = WzFile.open(WZ_PATH, region=REGION)
        self.renderer = CharacterRenderer(self.wz, region=REGION)
        self.region = REGION
        self.anim_cache = AnimCache(self.renderer)

        self.slots = {name: eid for name, eid in SLOTS}
        self.visible = {name: True for name, _ in SLOTS}
        self.slot_models = {}
        self.pose = "stand1"
        self.frame = 0
        self.flip = True
        self.ear_type = DEFAULT_EAR_TYPE
        self.show_overlays = True

        self._decode_cache = {}   # id(pixel_canvas) -> (canvas, PIL img, alpha bbox)

        self.placements = []
        self.world_anchors = {}
        self.part_items = {}

        self._build_ui()
        self._populate_slot_models()
        self._populate_poses()
        self._populate_ears()
        self.switch_mode("game")

    # ── UI 构建 ───────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        # 左: 装备选择(纸娃娃)
        left = self._make_equip_panel()
        root.addWidget(left)

        # 中: 堆叠视图(游戏 / 调试)
        self.stack = QStackedWidget()
        self.game_scene = QGraphicsScene(self)
        self.game_view = GameView(self.game_scene, self)
        self.debug_scene = QGraphicsScene(self)
        self.debug_view = DebugView(self.debug_scene, on_hover=self._on_hover)
        self.stack.addWidget(self.game_view)
        self.stack.addWidget(self.debug_view)
        root.addWidget(self.stack, 1)

        # 右: 明细表(仅调试模式)
        self._make_detail_panel()
        root.addWidget(self.detail_panel)

        self._build_toolbar()

        self.statusBar().showMessage("就绪")

    def _build_toolbar(self):
        tb = self.addToolBar("模式")
        tb.setMovable(False)
        self.game_btn = QPushButton("游戏模式")
        self.game_btn.setCheckable(True)
        self.game_btn.setChecked(True)
        self.game_btn.clicked.connect(lambda: self.switch_mode("game"))
        tb.addWidget(self.game_btn)
        self.debug_btn = QPushButton("调试模式")
        self.debug_btn.setCheckable(True)
        self.debug_btn.clicked.connect(lambda: self.switch_mode("debug"))
        tb.addWidget(self.debug_btn)
        tb.addSeparator()
        fit_btn = QPushButton("适应画布")
        fit_btn.clicked.connect(lambda: self.debug_view.fit())
        tb.addWidget(fit_btn)
        save_btn = QPushButton("保存 PNG…")
        save_btn.clicked.connect(self._save_png)
        tb.addWidget(save_btn)
        self.flip_check = QCheckBox("水平翻转(面向右)")
        self.flip_check.setChecked(self.flip)
        self.flip_check.toggled.connect(self._on_flip_toggled)
        tb.addWidget(self.flip_check)
        self.overlay_check = QCheckBox("显示标注")
        self.overlay_check.setChecked(self.show_overlays)
        self.overlay_check.toggled.connect(self._on_overlay_toggled)
        tb.addWidget(self.overlay_check)

    def switch_mode(self, mode):
        if mode == "game":
            self.game_btn.setChecked(True)
            self.debug_btn.setChecked(False)
            self.stack.setCurrentWidget(self.game_view)
            self.detail_panel.hide()
            self.game_view._draw_world()
            self.game_view._ensure_anim()
            self.game_view.setFocus()
        else:
            self.game_btn.setChecked(False)
            self.debug_btn.setChecked(True)
            self.stack.setCurrentWidget(self.debug_view)
            self.detail_panel.show()
            self.rebuild()

    # ── 装备选择面板 ─────────────────────────────────────────────────
    def _make_equip_panel(self) -> QWidget:
        box = QGroupBox("纸娃娃 · 装备选择")
        outer = QVBoxLayout(box)

        self.slot_tabs = QComboBox()
        self.slot_tabs.addItems([n for n, _ in SLOTS])
        self.slot_tabs.currentTextChanged.connect(self._on_slot_tab_changed)
        outer.addWidget(self.slot_tabs)

        # 顶部当前槽位信息 + 过滤
        info_row = QWidget()
        ir = QHBoxLayout(info_row)
        ir.setContentsMargins(0, 0, 0, 0)
        self.slot_equip_edit = QLineEdit()
        self.slot_equip_edit.setPlaceholderText("当前装备 ID")
        self.slot_equip_edit.setFixedWidth(120)
        self.slot_equip_edit.editingFinished.connect(self._on_slot_equip_edited)
        self.vis_check = QCheckBox("显示")
        self.vis_check.setChecked(True)
        self.vis_check.toggled.connect(self._on_visibility_toggled)
        ir.addWidget(self.slot_equip_edit)
        ir.addWidget(self.vis_check)
        ir.addStretch(1)
        outer.addWidget(info_row)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("筛选 (ID / 名称)")
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        outer.addWidget(self.filter_edit)

        self.list_view = QListView()
        self.list_view.setViewMode(QListView.ViewMode.ListMode)
        self.list_view.setIconSize(QSize(40, 40))
        self.list_view.setUniformItemSizes(False)
        self.list_view.setItemDelegate(EquipListItemDelegate())
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.clicked.connect(self._on_equip_clicked)
        outer.addWidget(self.list_view, 1)

        self.list_proxy = None
        scroll = QScrollArea()
        scroll.setWidget(box)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(360)
        return scroll

    def _populate_slot_models(self):
        for name, _ in SLOTS:
            cat = SLOT_CATEGORY[name]
            model = EquipListModel(self.renderer, self.wz, cat)
            self.slot_models[name] = model
        self._on_slot_tab_changed(self.slot_tabs.currentText())

    def _on_slot_tab_changed(self, slot_name):
        if slot_name not in self.slot_models:
            self.list_view.setModel(None)
            return
        model = self.slot_models[slot_name]
        proxy = QSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        proxy.setFilterKeyColumn(0)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self.list_proxy = proxy
        self.list_view.setModel(proxy)
        self._apply_filter(self.filter_edit.text())
        self.slot_equip_edit.setText(self.slots.get(slot_name, ""))
        self.vis_check.setChecked(self.visible.get(slot_name, True))
        # 选中当前装备
        cur_id = self.slots.get(slot_name)
        idx = model.find_id(cur_id) if cur_id else -1
        if idx >= 0:
            self.list_view.setCurrentIndex(proxy.mapFromSource(model.index(idx, 0)))
        self.list_view.scrollToTop()

    def _apply_filter(self, text):
        if self.list_proxy is None:
            return
        self.list_proxy.setFilterFixedString(text.strip())

    def _on_filter_changed(self, text):
        self._apply_filter(text)

    def _on_equip_clicked(self, index):
        # index 来自 proxy; 需要映射回源模型行再取 UserRole
        proxy = self.list_proxy
        idx = proxy.mapToSource(index) if proxy is not None else index
        slot = self.slot_tabs.currentText()
        equip_id = proxy.sourceModel().data(idx, Qt.ItemDataRole.UserRole)
        if not equip_id:
            return
        self.slots[slot] = equip_id
        self.slot_equip_edit.setText(equip_id)
        self.anim_cache.invalidate()
        self._decode_cache.clear()
        if self.handle_equip_change():
            self._switch_list_selection(slot, equip_id)
        # 重绘游戏/调试
        if self.stack.currentWidget() is not self.game_view:
            self.rebuild()

    def _switch_list_selection(self, slot, equip_id):
        model = self.slot_models[slot]
        idx = model.find_id(equip_id)
        proxy = self.list_proxy
        if idx >= 0 and proxy is not None:
            self.list_view.setCurrentIndex(proxy.mapFromSource(model.index(idx, 0)))

    def _on_slot_equip_edited(self):
        slot = self.slot_tabs.currentText()
        eid = self.slot_equip_edit.text().strip()
        self.slots[slot] = eid
        self.anim_cache.invalidate()
        self._decode_cache.clear()
        self.handle_equip_change()
        self._switch_list_selection(slot, eid)
        if self.stack.currentWidget() is not self.game_view:
            self.rebuild()

    def _on_visibility_toggled(self, checked):
        slot = self.slot_tabs.currentText()
        self.visible[slot] = checked
        self.handle_equip_change()

    def handle_equip_change(self):
        """装备变化后的通用刷新。返回 True 表示成功。"""
        self._populate_ears()
        self._populate_poses()
        self.frame = 0
        if self.stack.currentWidget() is self.game_view:
            self.game_view._ensure_anim()
        else:
            self.rebuild()
        return True

    # ── 姿态 / 耳型 ───────────────────────────────────────────────────
    def pick_attack_pose(self):
        weapon_id = next((e for e in self.equips() if category_for_id(e) == "Weapon"), None)
        poses = self.renderer.get_weapon_poses(weapon_id) if weapon_id else []
        for pref in (POSE_ATTACK, "swingO1", "swingO2", "swingO3", "stabO1", "stabO2"):
            if pref in poses:
                return pref
        return POSE_ATTACK

    def _populate_poses(self):
        weapon_id = next((e for e in self.slots.values()
                          if category_for_id(e) == "Weapon"), None)
        self.avail_poses = self.renderer.get_weapon_poses(weapon_id) if weapon_id else set(SUPPORTED_POSES)

    def _populate_ears(self):
        head_id = next((e for e in self.slots.values() if category_for_id(e) == "Head"), None)
        ears = self.renderer.get_ear_types(head_id) if head_id else []
        self.ears = ears or [DEFAULT_EAR_TYPE]

    # ── 数据访问 ──────────────────────────────────────────────────────
    def equips(self):
        return [eid for eid in self.slots.values() if eid]

    def _open(self, equip_id):
        return self.renderer._open_part(equip_id)

    def _decode(self, placement):
        key = id(placement.pixel_canvas)
        hit = self._decode_cache.get(key)
        if hit is not None:
            return hit
        img = decode_canvas(placement.pixel_canvas, region=self.region)
        arr = np.array(img)[:, :, 3]
        ys, xs = np.where(arr > 0)
        if len(xs) == 0:
            bbox = (0, 0, placement.pixel_canvas.width, placement.pixel_canvas.height)
        else:
            bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        entry = (placement.pixel_canvas, img, bbox)
        self._decode_cache[key] = entry
        return entry

    # ── 调试模式渲染 ─────────────────────────────────────────────────
    def rebuild(self):
        try:
            self._rebuild()
            self.statusBar().showMessage("已更新", 2000)
        except Exception as exc:
            self.statusBar().showMessage(f"渲染失败: {exc}", 8000)
            import traceback
            traceback.print_exc()

    def _rebuild(self):
        equips = self.equips()
        eff_pose = self.renderer.detect_pose(equips, self.pose)
        hide_hair_full, hide_hair_set, cap_vslot = \
            self.renderer._cap_hair_filter(equips)
        placements, anchors = self.renderer._build_placements(
            equips, eff_pose, self.ear_type,
            hide_hair_full, hide_hair_set, cap_vslot, self.frame,
            return_anchors=True,
        )
        self.placements = placements
        self.world_anchors = anchors
        self._populate_table()
        self._populate_anchor_table()
        self._draw_debug_scene()

    def _draw_debug_scene(self):
        self.debug_scene.clear()
        self.part_items = {}
        self._highlight_item = None
        fx = (lambda x: -x) if self.flip else (lambda x: x)

        overlay = self.show_overlays
        for pl in self.placements:
            if pl.top_left is None:
                continue
            if not self._visible_for(pl.equip_id):
                continue
            _, img, _ = self._decode(pl)
            w = pl.width_override if pl.width_override is not None else pl.pixel_canvas.width
            if self.flip:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            pix = pil_to_pixmap(img)
            item = PartItem(pix, pl, pl.category)
            draw_x = fx(pl.top_left[0]) - (w if self.flip else 0)
            item.setPos(QPointF(draw_x, pl.top_left[1]))
            item.setOpacity(0.9)
            self.debug_scene.addItem(item)
            self.part_items[id(pl)] = item

            if overlay:
                self._draw_overlay(pl, fx)

        self._add_cross(self.debug_scene, QPointF(fx(0), 0), QColor("#ffffff"), 6)
        self._add_grid(self.debug_scene, fx)
        self.debug_view.fit()

    def _visible_for(self, equip_id):
        for name, eid in self.slots.items():
            if eid == equip_id:
                return self.visible.get(name, True)
        return True

    def _draw_overlay(self, pl, fx):
        y0 = pl.top_left[1]
        ox, oy = pl.origin
        self._add_dot(self.debug_scene, fx(pl.top_left[0] + ox), y0 + oy, QColor("#ff3333"), 2.2, z=102)
        for name, vec in pl.map_anchors.items():
            aw = pl.top_left[0] + ox + vec[0]
            ah = pl.top_left[1] + oy + vec[1]
            ac = ANCHOR_COLORS.get(name, QColor("#00ff00"))
            self._add_dot(self.debug_scene, fx(aw), ah, ac, 1.8, z=103)
        used = _determine_anchor(pl.canvas, pl.category)
        if used in pl.map_anchors:
            aw = pl.top_left[0] + ox + pl.map_anchors[used][0]
            ah = pl.top_left[1] + oy + pl.map_anchors[used][1]
            self._add_dot(self.debug_scene, fx(aw), ah, QColor("#ffffff"), 4.0, z=104)

    def _add_dot(self, scene, x, y, color, r, z=0):
        dot = QGraphicsEllipseItem(x - r, y - r, r * 2, r * 2)
        dot.setPen(QPen(QColor("#000000"), 0))
        dot.setBrush(QBrush(color))
        dot.setZValue(z)
        scene.addItem(dot)

    def _add_cross(self, scene, pos, color, r):
        x, y = pos.x(), pos.y()
        pen = QPen(color, 0)
        scene.addLine(x - r, y, x + r, y, pen)
        scene.addLine(x, y - r, x, y + r, pen)

    def _add_grid(self, scene, fx):
        pen = QPen(QColor(255, 255, 255, 26), 0)
        for g in range(-5, 6):
            if g == 0:
                continue
            scene.addLine(fx(g * 8), -200, fx(g * 8), 200, pen)
            scene.addLine(fx(-200), g * 8, fx(200), g * 8, pen)

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.placements))
        for i, pl in enumerate(self.placements):
            if pl.top_left is None:
                continue
            chk = QCheckBox()
            chk.setChecked(self._visible_for(pl.equip_id))
            chk.stateChanged.connect(lambda _s, pid=id(pl): self._on_row_toggle(pid))
            self.table.setCellWidget(i, 0, chk)
            for j, val in enumerate([
                pl.category, pl.name, str(pl.z_slot),
                f"{pl.top_left[0]},{pl.top_left[1]}",
            ]):
                it = QTableWidgetItem(str(val))
                it.setData(Qt.ItemDataRole.UserRole, id(pl))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, j + 1, it)
            row_color = CATEGORY_COLORS.get(pl.category, QColor("#808080"))
            self.table.item(i, 1).setForeground(QBrush(row_color))
        self.table.blockSignals(False)

    def _populate_anchor_table(self):
        self.anchor_table.setRowCount(0)
        self.anchor_table.setRowCount(len(self.world_anchors))
        for i, (name, (x, y)) in enumerate(sorted(self.world_anchors.items())):
            for j, val in enumerate([name, str(x), str(y)]):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.anchor_table.setItem(i, j, it)

    def _make_detail_panel(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.addWidget(QLabel("部位明细"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["显示", "部位", "名称", "z", "top_left"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemClicked.connect(self._on_table_click)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table)
        lay.addWidget(QLabel("世界锚点"))
        self.anchor_table = QTableWidget(0, 3)
        self.anchor_table.setHorizontalHeaderLabels(["锚点", "x", "y"])
        self.anchor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.anchor_table.verticalHeader().setVisible(False)
        self.anchor_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.anchor_table)
        self.hover_label = QLabel("")
        self.hover_label.setWordWrap(True)
        lay.addWidget(self.hover_label)
        self.detail_panel = wrap
        return wrap

    def _on_hover(self, placement):
        if placement is None:
            self.hover_label.setText("")
            return
        fx = (lambda x: -x) if self.flip else (lambda x: x)
        ox, oy = placement.origin
        used = _determine_anchor(placement.canvas, placement.category)
        lines = [
            f"{placement.category} / {placement.name}  z={placement.z_slot}",
            f"equip={placement.equip_id}",
            f"top_left=({fx(placement.top_left[0])},{placement.top_left[1]})  "
            f"origin=({ox},{oy})",
            f"锚点={used}  map={ {k: v for k, v in placement.map_anchors.items()} }",
        ]
        self.hover_label.setText("\n".join(lines))

    def _on_table_click(self, item):
        pid = item.data(Qt.ItemDataRole.UserRole)
        pl = next((p for p in self.placements if id(p) == pid), None)
        if pl is None:
            return
        self._highlight(pl)

    def _highlight(self, pl):
        if self._highlight_item is not None:
            self.debug_scene.removeItem(self._highlight_item)
            self._highlight_item = None
        if pl is None or pl.top_left is None:
            return
        fx = (lambda x: -x) if self.flip else (lambda x: x)
        w = pl.width_override if pl.width_override is not None else pl.pixel_canvas.width
        h = pl.height_override if pl.height_override is not None else pl.pixel_canvas.height
        left = fx(pl.top_left[0]) - (w if self.flip else 0)
        rect = QGraphicsRectItem(QRectF(left - 1, pl.top_left[1] - 1, w + 2, h + 2))
        rect.setPen(QPen(QColor("#ffffff"), 1))
        rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        rect.setZValue(500)
        self.debug_scene.addItem(rect)
        self._highlight_item = rect

    def _on_row_toggle(self, pid):
        pl = next((p for p in self.placements if id(p) == pid), None)
        if pl is None:
            return
        self._toggle_for(pl.equip_id)

    def _toggle_for(self, equip_id):
        for name, eid in self.slots.items():
            if eid == equip_id:
                self.visible[name] = not self.visible.get(name, True)
        self.rebuild()

    def _on_flip_toggled(self, checked):
        self.flip = checked
        self.game_view._ensure_anim()
        if self.stack.currentWidget() is not self.game_view:
            self.rebuild()

    def _on_overlay_toggled(self, checked):
        self.show_overlays = checked
        if self.stack.currentWidget() is not self.game_view:
            self.rebuild()

    def _save_png(self):
        canvas = self._composite_image()
        if canvas is None:
            self.statusBar().showMessage("没有可渲染的部位", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存 PNG", "", "PNG (*.png)")
        if path:
            canvas.save(path)
            self.statusBar().showMessage(f"已保存 {path}", 4000)

    def _composite_image(self):
        bbox = None
        for pl in self.placements:
            if pl.top_left is None or not self._visible_for(pl.equip_id):
                continue
            w = pl.width_override if pl.width_override is not None else pl.pixel_canvas.width
            h = pl.height_override if pl.height_override is not None else pl.pixel_canvas.height
            if bbox is None:
                bbox = [pl.top_left[0], pl.top_left[1],
                        pl.top_left[0] + w, pl.top_left[1] + h]
            else:
                bbox[0] = min(bbox[0], pl.top_left[0])
                bbox[1] = min(bbox[1], pl.top_left[1])
                bbox[2] = max(bbox[2], pl.top_left[0] + w)
                bbox[3] = max(bbox[3], pl.top_left[1] + h)
        if bbox is None:
            return None
        min_x, min_y, max_x, max_y = bbox
        gw, gh = int(max_x - min_x), int(max_y - min_y)
        canvas = Image.new("RGBA", (max(1, gw), max(1, gh)), (0, 0, 0, 0))
        for pl in self.placements:
            if pl.top_left is None or not self._visible_for(pl.equip_id):
                continue
            _, img, _ = self._decode(pl)
            canvas.alpha_composite(img, (int(pl.top_left[0] - min_x), int(pl.top_left[1] - min_y)))
        if self.flip:
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)
        return canvas

    # ── 键盘输入(已移至 GameView) ───────────────────────────────────


# 原 PartItem(被 _draw_debug_scene 使用)
class PartItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, placement, category):
        super().__init__(pixmap)
        self.placement = placement
        self.category = category
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)


def main():
    app = QApplication(sys.argv)
    win = DebugApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
