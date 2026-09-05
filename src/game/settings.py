"""全局配置：地图、窗口、物理常数。

坐标约定：沿用 WZ 世界坐标（y 向下为正），navel 为角色世界锚点。
窗口 = 内部视口(VIEW_W×VIEW_H) 按 WINDOW_SCALE 放大到物理窗口。
"""

from pathlib import Path

# ── 路径 ─────────────────────────────────────────────────────────────
# 代码位于 src/game，故向上三阶回到项目根（src/game → src → 项目根）。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# 资源目录（与 src 同级）：wz 官方资产 + content 规则脚本，均为只读运行数据。
RESOURCE_DIR = PROJECT_ROOT / "resources"
WZ_DIR = RESOURCE_DIR / "wz"
REGION = "EMS"
# 自绘鼠标光标的 PNG 目录（官方光标不在 WZ 里，来自客户端 cursor.wzl 的提取件）
CURSOR_DIR = RESOURCE_DIR / "cursor"
CURSOR_FRAME_MS = 160           # 光标动画每帧毫秒数

SAVE_DIR = PROJECT_ROOT / "saves"
SAVE_FILE = SAVE_DIR / "save.json"
KEYBINDINGS_FILE = SAVE_DIR / "keybindings.json"   # 全局键位（跨角色共用）
SAVE_INTERVAL = 60.0          # 定时自动存档秒数

MAP_ID = "100010000"            # 弓箭手村东部小山（49 怪 + 2 NPC）
# MAP_ID = "100000000"          # 弓箭手村（城镇，无怪）

# ── 窗口 / 视口 ──────────────────────────────────────────────────────
# 内部视口直接 = 窗口像素，scale=1 让画面按原生尺寸显示（不再放大）。
VIEW_W = 800
VIEW_H = 600
WINDOW_SCALE = 1
WINDOW_W = VIEW_W * WINDOW_SCALE
WINDOW_H = VIEW_H * WINDOW_SCALE
FPS = 60
FADE_TIME = 0.4                 # 地图切换 / 重生后的黑场淡入秒数

# ── 角色物理（世界坐标，y 向下）────────────────────────────────────
GRAVITY = 2200.0                 # px/s^2
MOVE_SPEED = 300.0               # 地面水平速度 px/s
MOVE_ACCEL = 2600.0              # 地面水平加速度 px/s^2（速度缓动，避免瞬起瞬停）
AIR_ACCEL = 0.55                 # 空中水平加速度倍率（对 MOVE_ACCEL 打折扣）
JUMP_VELOCITY = -900.0           # 起跳初速度（向上为负）
COYOTE_TIME = 0.08               # 离开地面后仍可起跳的窗口（秒）
JUMP_BUFFER_TIME = 0.12          # 落地前一瞬按跳仍生效的缓冲（秒）
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
# 角色贴图半宽（新手 stand 帧实测 ~39px）：顶到地图可行走边界时按此内缩，
# 让身体边缘贴平台边即停，不再半身悬出边缝（边缝处没有墙体贴图可遮）
PLAYER_VISUAL_HALF_W = 20.0
# 墙顶/底相对脚底的容差：ytop∈[feet-EPS,feet] 视为平台边缘 stub 放行；
# ybottom 高于 feet-EPS 视为上层平台悬挂边缘放行
WALL_FEET_EPS = 3.0
# 链接续段的最大自动上/下步高差（≥原版一级台阶 25~35px；更高需跳跃）
PLAYER_STEP_UP = 36.0
# 出生点贴地吸附容差：WZ portal 标注 y 常落在 foothold 线上下数 px~数十 px，
# 首帧没有穿线信息，落点在容差内取最近面双向吸附，防止一进图就穿地坠落
SPAWN_SNAP_TOL = 60.0

# ── 战斗 ─────────────────────────────────────────────────────────────
ATTACK_RANGE = 58.0              # 攻击命中框向前延伸距离
ATTACK_HEIGHT = 30.0
BASE_DAMAGE = 25                 # 基础攻击力
ATTACK_MOVE_FRICTION = 8.0       # 攻击期间水平速度每秒摩擦衰减系数（保留惯性滑行至停）
# 经验需求：官方逐级表见 game/stats.py EXP_TO_NEXT，此处不再用指数近似
RESPAWN_FULL = True

# ── 数值系统（四维 / AP / HP·MP 成长，公式见 game/stats.py）─────────
BASE_STATS = {"str": 4, "dex": 4, "int": 4, "luk": 4}
AP_PER_LEVEL = 5                 # 每级获得属性点
HP_BASE = 50                     # HP 基础值（Lv0 截距）
MP_BASE = 30                     # MP 基础值
BASE_WEAPON_PAD = 10             # 空手面板攻击（须低于新手武器 PAD，拿剑才有提升感）

# ── 玩家受击（原版行为：击退小跳 + 短暂无敌闪烁）───────────────────
HURT_STUN = 0.30                 # 受击硬直秒数（期间锁移动/攻击）
HURT_INVULN = 1.20               # 受击后无敌秒数（闪烁）
HURT_KNOCKBACK = 200.0           # 击退水平初速度 px/s
HURT_HOP_VY = -170.0             # 受击小跳初速度

# ── 怪物 ─────────────────────────────────────────────────────────────
MOB_AGGRO_RANGE = 160.0          # 仇恨范围（水平）
MOB_AGGRO_Y_RANGE = 60.0         # 仇恨范围（垂直，脚底 y 差）
# 怪物 WZ speed 是有符号偏移值（实测全体约 -80..140，多数 0 或负），
# 非"100=步行"百分比。仿射映射到 px/s：move = BASE + speed × FACTOR，
# 使 -50 慢逛、0 常速、+100 快冲，两端再钳制，避免静止或飞太快。
MOB_SPEED_BASE = 50.0            # speed=0 时的移动 px/s（约等于旧巡逻手感）
MOB_SPEED_FACTOR = 0.4           # 每点 speed 偏移增减的 px/s
MOB_SPEED_MIN = 14.0             # 漫游速度下限（保证"会动"）
MOB_SPEED_MAX = 100.0            # 追击/漫游速度上限
MOB_WANDER_PAUSE = (1.0, 4.0)    # 漫游两段行走之间随机站桩时长（秒）
MOB_ATTACK_RANGE = 40.0          # 接触伤害距离（水平）
MOB_CONTACT_Y_RANGE = 40.0       # 接触伤害距离（垂直，脚底 y 差）
MOB_KNOCKBACK = 60.0             # 受击击退
SPAWN_GRACE = 3.0                # 出生/重生后怪物不追击不攻击的秒数
MOB_RESPAWN_DELAY = 5.0          # 怪物死亡后原地重生延迟秒数

# ── 掉落 / 场景 ──────────────────────────────────────────────────────
DROP_LIFETIME = 20.0             # 掉落物存活秒数
DROP_PLAYER_LIFETIME = 120.0     # 玩家扔出物品的存活秒数（防误扔瞬间消失）
DROP_THROW_SPEED = -340.0        # 玩家扔出物品的上抛初速度（竖直向上）
# 金币图标按面额分档（对应 Item/Special/0900 的 09000000~09000003：单枚→单枚→小堆→大堆）。
# 取「金额 < 上界」命中的第一档；超上限走最后一档（大额堆）。
MESO_ICON_TIERS = ((100, 0), (1000, 1), (10000, 2), (float("inf"), 3))
# 物品掉率：每次击杀对掉落表逐件独立掷骰（近似原版模型），最多掉一件。
# 原版逐 item dropRate 在服务端、客户端 WZ 不含，故按 item id 首位分类给概率。
DROP_ITEM_RATE = {
    "1": 0.0003,   # 装备：万分之三
    "2": 0.04,     # 消耗
    "3": 0.001,    # 商城（几乎不掉）
    "4": 0.50,     # 其他（贝壳/矿石类，最常掉）
    "5": 0.05,     # 宠物/特殊
    "6": 0.05,     # 奖励
    "8": 0.01,     # 装饰/称号
}
DROP_ITEM_DEFAULT_RATE = 0.05    # 未登记类别的兜底掉率
PICKUP_RANGE = 30.0             # Z 键拾取水平半径（一次只捡其中最近的一件）
PICKUP_ATTRACT_TIME = 0.22       # 拾取吸附动画时长（秒）
PICKUP_HOLD_INTERVAL = 0.1       # 按住 Z 连捡时两次拾取的最小间隔（秒）
FALL_OUT_DAMAGE = 30             # 掉出地图底部回出生点时的扣血

# ── 背包 / 装备 ──────────────────────────────────────────────────────
INVENTORY_EQUIP_CAP = 24         # 装备栏（未穿戴散件）上限
START_CONSUMES = {"2000000": 12}  # 初始背包：红色药水 ×12
# 默认外观：前 4 项为身体/头/脸/发基底，其余为初始穿戴装备
# （出生即发一把木剑，转职时由职业 starter_weapon 换发）
DEFAULT_EQUIPS = [
    "00002000", "00012000", "00030000", "00020000",
    "01040000", "01060000", "01070000", "01302000",
]

# ── 技能 ─────────────────────────────────────────────────────────────
SP_PER_LEVEL = 3                 # 每级获得 SP
SKILL_MP_REGEN = 1.2             # MP 自然回复 / 秒
SKILL_COOLDOWN: dict = {}        # 施放冷却覆盖表（秒）；缺省回退 0.8
SKILL_MAX_LEVEL = 20             # 技能最高等级（裁剪 WZ level 表）
ATTACK_CANCEL_DELAY = 0.25       # 攻击起手后允许被下一击取消后摇的最短秒数
SKILL_INPUT_BUFFER = 0.4         # 技能键在攻击锁定期内按下时的输入缓冲时长（秒）

# ── Buff / 状态异常（game/buffs.py）──────────────────────────────────
CRIT_MULT = 1.5                  # 暴击伤害倍率
POISON_TICK = 1.0                # 中毒结算间隔（秒）
SLOW_MULT = 0.5                  # 减速期间移速倍率

# 怪物异常技能 id（Skill.wz/MobSkill.img，官方客户端映射）→ 玩家异常种类。
# 123=stun(眩晕) 125=poison(中毒) 126=slow(减速)；其余 mob skill 忽略。
MOB_STATUS_SKILLS = {"123": "stun", "125": "poison", "126": "slow"}

# ── 商店 / 仓库 / 卷轴（game/shop.py、inventory.py）──────────────────
SELL_RATE = 0.5                  # 出售价 = 买价 × 该系数
STORAGE_CAP = 48                 # 仓库格数上限

# 自制强化卷轴（Item.wz 无 234 类目，id 段 2340000~2349999 自造不冲突）
SCROLL_ID_MIN = 2340000          # 卷轴 id 段下限（含）
SCROLL_ID_MAX = 2350000          # 卷轴 id 段上限（不含）
SCROLL_FEE_BASE = 500            # 卷轴强化费基础（金币）
SCROLL_FEE_PER_LEVEL = 200       # 卷轴强化费每级增量（金币）
# 缺 price 字段的物品兜底买价（WZ 有 price 优先；键用补零 8 位 id）
FALLBACK_PRICES = {
    "02340000": 50000,           # 武器攻击力卷轴 60%
    "02340001": 150000,          # 武器攻击力卷轴 30%
    "02340002": 20000,           # 武器攻击力卷轴 100%
}
# 「其他」类（04xxxxxx）物品：官方 WZ 无 price 字段（卖出价在服务端 NPC shop
# 数据中，客户端不含），按 id 前 5 位分档给兜底买价（出售价再 ×SELL_RATE）。
ETC_PRICE_TIERS = {
    "04003": 60,     # 羽毛 / 冰块类
    "04004": 400,    # 属性母矿
    "04005": 600,    # 水晶
    "04006": 500,    # 魔法石 / 召唤石
    "04007": 300,    # 魔法粉
    "04010": 500,    # 金属母矿
    "04020": 800,    # 宝石母矿
    "04021": 1200,   # 宝石成品
    "04030": 100,    # 杂项素材
    "04032": 200,    # 机械零件
    "04130": 1000,   # 制作催化剂
    "04131": 1500,   # 制作配方书
    "04161": 2000,   # 技能书 / 技法书
}
# 分档内的稀有素材单件覆盖（仍归 04000 段但远贵于普通怪兽素材）
ETC_PRICES = {
    "04000014": 1500,            # 暴龙的头骨
    "04000030": 800,             # 龙皮
    "04000186": 2500,            # 黑龙之角
    "04000244": 3000,            # 龙魂石
    "04000245": 3000,            # 闪耀的龙鳞
    "04020009": 5000,            # 时间碎片
    "04020010": 4000,            # 被封印的勇者之石
    "04020011": 4000,            # 被封印的贤者之石
    "04020012": 4000,            # 被封印的圣者之石
}
ETC_DEFAULT_PRICE = 20           # 未分档的普通怪兽素材（壳 / 皮 / 树枝…）

# ── 职业 / 转职 ──────────────────────────────────────────────────────
BOWMAN_JOB = 3000                # 弓箭手 1 转职业码
BOWMAN_STARTER_BOW = "1452002"   # 转职附赠木弓（需求 Lv10；短弓 1452000 需 Lv25/DEX80）
BOWMAN_TRAINER_NPC = "1012100"   # 导师赫丽娜
TRAINER_SPAWN_MAP = "100010000"  # 导师注入的地图（出生图：弓箭手村东部小山）
TRAINER_SPAWN = (-520.0, 455.0)  # 导师站立点（出生 portal 旁地面 foothold，脚底坐标）

# ── 远程弹道（直线快箭 + 穿透计数）──────────────────────────────────
ARROW_SPEED = 900.0              # 箭矢飞行速度 px/s（瞄准后为合速）
ARROW_AIM_RADIUS = 360.0         # 原版式瞄准半径：扇形内最近的怪会被瞄
ARROW_AIM_HALF_ANGLE_DEG = 15.0  # 瞄准扇形半顶角：以朝向水平线为轴 ±15°
ARROW_LIFETIME = 0.4             # 箭矢存活秒数（超程消失）
NORMAL_ARROW_ITEM_ID = "02060000"  # 普攻箭矢贴图来源：金币箭物品的 bullet 节点
SNAIL_THROW_SKILL_ID = "10001000"  # 蜗牛投掷术（台版 1000.img「嫩寶丟擲術」）
SNAIL_THROW_MOB_ID = "0100101"     # 弹道贴图来源：藍寶的 stand 帧（WZ 无 ball 节点）
SNAIL_THROW_SPEED = 420.0          # 蜗牛飞行速度（比箭慢得多，符合气质）
SNAIL_THROW_LIFETIME = 0.55        # 蜗牛存活秒数（投程比箭远一点）

# ── 小地图 ─────────────────────────────────────────────────────────
MINIMAP_W = 178                # 小地图窗口宽
MINIMAP_H = 120                # 小地图窗口高
MINIMAP_MARGIN = 8             # 右上角留白
MINIMAP_MAG_FALLBACK = 4       # 无 WZ miniMap.mag 时的缩放倍率
MINIMAP_MAG_EXTRA = 2          # 额外拉远倍率：视野范围 ×该值（面板不变，看得更广）
MINIMAP_BG_ALPHA = 150         # 底半透明深色透明度
MINIMAP_PLATFORM_COLOR = (170, 190, 210)   # 平台线
MINIMAP_ROPE_COLOR = (120, 140, 160)       # 绳/梯竖线
MINIMAP_PLAYER_COLOR = (255, 205, 60)      # 玩家箭头
MINIMAP_MOB_COLOR = (230, 70, 60)          # 怪物
MINIMAP_NPC_COLOR = (245, 215, 60)         # NPC
MINIMAP_PORTAL_COLOR = (90, 220, 100)      # 传送门

# ── 任务系统 ─────────────────────────────────────────────────────────
# 任务池不再手工白名单：启动时全量解析 Quest.wz，并按 Map.wz 真实出现的
# NPC / 怪物过滤（见 core.life_index + systems.quests.filter_world_quest_defs）。
# ── 地图通行 / 缓存 ────────────────────────────────────────────────
# 连通关系由 Map.wz portal 的 tm/tn 数据驱动（见 game/travel.py），
# 不再使用白名单。以下为整图 Surface LRU 缓存与切图横幅参数。
MAP_CACHE_BUDGET_PX = 50_000_000   # 缓存整图像素预算（RGBA 约 200MB 上限）
BANNER_TIME = 3.0                  # 切图「街道名·地图名」横幅时长（秒）

# 出租车传送目的地改由 content/npc/<id>.lua 的 entries() 定义（type="teleport"），
# Python 不再持有出租车名单与目的地表。
