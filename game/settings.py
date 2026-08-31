"""全局配置：地图、窗口、物理常数。

坐标约定：沿用 WZ 世界坐标（y 向下为正），navel 为角色世界锚点。
窗口 = 内部视口(VIEW_W×VIEW_H) 按 WINDOW_SCALE 放大到物理窗口。
"""

from pathlib import Path

# ── 路径 ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WZ_DIR = PROJECT_ROOT / "wz"
REGION = "EMS"

SAVE_DIR = PROJECT_ROOT / "saves"
SAVE_FILE = SAVE_DIR / "save.json"
SAVE_INTERVAL = 60.0          # 定时自动存档秒数

MAP_ID = "100010000"            # 弓箭手村東部小山（49 怪 + 2 NPC）
# MAP_ID = "100000000"          # 弓箭手村（城镇，无怪）

# ── 窗口 / 视口 ──────────────────────────────────────────────────────
# 内部视口直接 = 窗口像素，scale=1 让画面按原生尺寸显示（不再放大）。
VIEW_W = 960
VIEW_H = 540
WINDOW_SCALE = 1
WINDOW_W = VIEW_W * WINDOW_SCALE
WINDOW_H = VIEW_H * WINDOW_SCALE
FPS = 60

# ── 角色物理（世界坐标，y 向下）────────────────────────────────────
GRAVITY = 2200.0                 # px/s^2
MOVE_SPEED = 150.0               # 地面水平速度 px/s
AIR_ACCEL = 0.55                 # 空中水平加速度倍率
JUMP_VELOCITY = -700.0           # 起跳初速度（向上为负）
MAX_FALL_SPEED = 1600.0
LADDER_SPEED = 130.0             # 爬梯速度
CLIMB_TOP_OVERSHOOT = 40.0       # 爬出绳/梯顶端的最大越出距离（用于落到顶部平台）
DROP_THROUGH_TIME = 0.30         # 下跳穿过平台的无碰撞秒数
# 贴墙互动（原版没有、类 MS 平台跳跃的通用增强，可按手感关改这里）
WALL_SLIDE_SPEED = 140.0         # 空中贴着墙按住方向键下落时的限速
WALL_JUMP_VX = 260.0             # 蹬墙跳水平弹开速度
WALL_JUMP_LOCK = 0.15            # 蹬墙跳后朝原墙方向输入的失控时长

# 角色 navel → 脚底偏移（像素，实测 stand1 约 20px）
FEET_OFFSET = 20.0
# 角色受击/碰撞盒（相对 navel 的偏移）
PLAYER_HIT_W = 26.0
PLAYER_HIT_H = 48.0
# 角色身体半宽（用于竖直墙的水平阻挡）
PLAYER_BODY_HALF_W = 10.0
# 墙顶/底相对脚底的容差：ytop∈[feet-EPS,feet] 视为平台边缘 stub 放行；
# ybottom 高于 feet-EPS 视为上层平台悬挂边缘放行
WALL_FEET_EPS = 3.0
# 链接续段的最大自动上/下步高差（≥原版一级台阶 25~35px；更高需跳跃）
PLAYER_STEP_UP = 36.0

# ── 战斗 ─────────────────────────────────────────────────────────────
ATTACK_RANGE = 58.0              # 攻击命中框向前延伸距离
ATTACK_HEIGHT = 30.0
BASE_DAMAGE = 25                 # 基础攻击力
PLAYER_MAX_HP = 100
PLAYER_MAX_MP = 50
BASE_EXP_NEED = 15               # 1 级所需经验
EXP_GROWTH = 1.35                # 每级经验需求增长倍率
RESPAWN_FULL = True

# ── 玩家受击（原版行为：击退小跳 + 短暂无敌闪烁）───────────────────
HURT_STUN = 0.30                 # 受击硬直秒数（期间锁移动/攻击）
HURT_INVULN = 1.20               # 受击后无敌秒数（闪烁）
HURT_KNOCKBACK = 200.0           # 击退水平初速度 px/s
HURT_HOP_VY = -170.0             # 受击小跳初速度

# ── 怪物 ─────────────────────────────────────────────────────────────
MOB_AGGRO_RANGE = 160.0          # 仇恨范围（水平）
MOB_AGGRO_Y_RANGE = 60.0         # 仇恨范围（垂直，脚底 y 差）
MOB_CHASE_SPEED = 70.0
MOB_PATROL_SPEED = 30.0
MOB_ATTACK_RANGE = 40.0          # 接触伤害距离（水平）
MOB_CONTACT_Y_RANGE = 40.0       # 接触伤害距离（垂直，脚底 y 差）
MOB_CONTACT_DAMAGE = 8
MOB_KNOCKBACK = 60.0             # 受击击退
SPAWN_GRACE = 3.0                # 出生/重生后怪物不追击不攻击的秒数

# ── 掉落 / 场景 ──────────────────────────────────────────────────────
DROP_LIFETIME = 20.0             # 掉落物存活秒数
DROP_ITEM_CHANCE = 0.45          # 击杀掉落物品概率（金币必掉）
PICKUP_RANGE = 34.0
FALL_OUT_DAMAGE = 30             # 掉出地图底部回出生点时的扣血

# ── 背包 / 装备 ──────────────────────────────────────────────────────
INVENTORY_EQUIP_CAP = 24         # 装备栏（未穿戴散件）上限
START_CONSUMES = {"2000000": 12}  # 初始背包：红色药水 ×12
# 默认外观：前 4 项为身体/头/脸/发基底，其余为初始穿戴装备
DEFAULT_EQUIPS = [
    "00002000", "00012000", "00030000", "00020000",
    "01040000", "01060000", "01070000", "01302000",
]

# ── 技能 ─────────────────────────────────────────────────────────────
SP_PER_LEVEL = 3                 # 每级获得 SP
SKILL_MP_REGEN = 1.2             # MP 自然回复 / 秒
SKILL_COOLDOWN = {"1001004": 0.6, "1001005": 1.2}   # 施放冷却（秒）
SKILL_UNLOCK_LEVEL = {"1001004": 1, "1001005": 5}   # 可学习等级
SKILL_MAX_LEVEL = 20             # 技能最高等级（裁剪 WZ level 表）
# 快捷键位：技能 id → 数字键（pygame.K_1 / K_2）
SKILL_HOTKEYS = {"1001004": 1, "1001005": 2}
HOTKEY_SKILLS = {1: "1001004", 2: "1001005"}        # 反向映射：键 → 技能

# ── 任务系统 ─────────────────────────────────────────────────────────
# 启用的精选任务（Quest.wz 内真实任务 id）。引擎可解析全部任务，
# 这里只开放能在 弓箭手村 区域完整游玩的任务。
ENABLED_QUESTS = {
    "2088",    # 研究菇菇怪物：布魯斯(1012111) 收集 蘑菇芽孢x10 + 菇菇寶貝傘x40
    "10037",   # 尤莉亞的幫助（村内对话演示）
    "10083",   # 长老斯坦的加油（村内对话演示）
    "10205",   # 精灵的项坠（村内对话 + 奖励）
    "52043",   # 快速前往旅館！
}
# 可传送的地图白名单（Henesys 区域，含 弓箭手村/東部小山/東部草叢/可疑的山丘/市集/邱比特公園）
TRAVEL_MAPS = {
    "100000000", "100010000", "100020000", "100010100",
    "100000100", "100000200",
}
