# 数值系统（四维属性 / AP / 攻防公式 / 穿戴门控）设计文档

- 日期：2026-08-31
- 状态：已批准并已实现（方案 A：简化但完整）
- 分支：`feat/stats-system`（worktree `../maplestory-stats`）

## 1. 背景与目标

当前游戏没有真正的数值系统：HP/MP 固定（100/50），伤害为占位公式
`attack_value = 10 + 等级×2 + 装备PAD×3`，无四维属性、无加点，装备可无条件穿戴。

本设计引入完整的「属性 → 派生数值 → 战斗结算」链路，公式取简化版而非官方
v113 全量还原（已与使用者确认选方案 A）。状态面板 UI **必须使用 UI.wz 原版素材**。

## 2. 范围

**In**
- 四维属性 STR/DEX/INT/LUK + 每级 5AP 手动加点 / 一键自动
- HP/MP 按职业成长公式（含装备 hp/mp 词条）
- 玩家→怪物伤害公式（武器 incPAD × 主属性权重 + 副属性/10，技能倍率，
  随机 95%~105%，怪物 PDD 按 LUK 减免）
- 装备穿戴门控（reqLevel / reqSTR / reqDEX / reqINT / reqLUK）
- 状态面板（S 键）：`UIWindow.img/Stat` 原版底图 + BtApUp 四态按钮 + BtAuto
- 存档 v2→v3（新增 stats/ap，旧档按职业自动分配迁移）
- 转职奖励武器 1452000 → 1452002 木弓（原短弓需求 Lv25/DEX80，Lv10 无法装备）

**Out（本轮不做）**
- 官方完整伤害公式（武器系数表、蒙面值、属性克制）
- 二级属性（ACC/EVA/攻速）、负重、属性耐性
- 法师 INT 体系（公式已兼容，无职业技能树）

## 3. 数值定义（settings.py + jobs.py）

| 常量 | 值 | 说明 |
|---|---|---|
| `AP_PER_LEVEL` | 5 | 每级获得属性点 |
| `HP_BASE` / `MP_BASE` | 50 / 30 | 基础值（Lv0 截距） |
| 新手 hp/mp 成长 | 15 / 10 每级 | `JobDef.hp_gain/mp_gain` |
| 弓箭手 hp/mp 成长 | 20 / 12 每级 | 同上 |
| `BASE_WEAPON_PAD` | 25 | 空手基础攻击（未穿武器时） |

- `max_hp = HP_BASE + 等级 × hp_gain + 装备hp词条`（MP 同理）
- 四维基础值：新手 4/4/4/4；升级不自动加属性（AP 手动/自动分配）
- 自动分配 `JobDef.auto_ap`：新手 `{"str":5}`、弓箭手 `{"dex":5}`

## 4. 公式（game/stats.py，纯函数、无 WZ 依赖）

```
主属性 main = 弓/弩 ? DEX : STR；副属性 sub = 另一维
atk  = pad × (1 + 4×main/100) + sub/10          # pad = 武器incPAD 或 BASE_WEAPON_PAD
dmg  = max(1, int(atk × 技能倍率 × rand(0.95~1.05)) − mob_pd × (1 − LUK/100))
def  = 装备PDD总和 + DEX//10                      # defense_value
玩家受伤：保留现有 100/(100+def) 减伤曲线
```

穿戴门控 `wear_block(item, level, stats) -> Optional[str]`：逐项检查
reqLevel/reqSTR/reqDEX/reqINT/reqLUK，返回缺失提示（如「敏捷不足（需 80）」）。

## 5. WZ 数据（已实测验证）

- `UI.wz/UIWindow.img/Stat`：`backgrnd` 175×337（含名称/职业/等级/公会/HP/MP/
  经验值/名誉 + 升级点数 + 力量/敏捷/智力/幸运 全部标签）；`BtApUp` 12×12
  四态；`BtAuto` 73×35；`Disabled/STR|DEX|INT|LUK` 48×16。
- 逐像素实测（backgrnd 175×337）：标签块 x∈[4,56]，数值槽 x∈[58,170]；
  行 y 起点：名称 33 / 职业 52 / 等级 69 / 公会 87 / HP 105 / MP 123 /
  经验值 141 / 名誉 163（行高 14）；AP 白框 (63,206,25,13)；
  四维绿行 y 起点：力量 235 / 敏捷 253 / 智力 271 / 幸运 289。
- `Mob.wz` stats 已有 `weaponDefense`（PDD）映射（wzpy/mob.py `_STAT_FIELDS`）。
- `Character.wz` 装备 info 已含 reqLevel/reqSTR/reqDEX/reqINT/reqLUK/incPAD/
  incPDD/hp/mp/str/dex/int/luk 词条（`assets.equip_info` 现成）。

## 6. 改动文件

| 文件 | 改动 |
|---|---|
| `game/stats.py` | **新增**：全部纯函数 |
| `game/settings.py` | 新增数值常量区块 |
| `game/jobs.py` | `JobDef` 加 `hp_gain/mp_gain/auto_ap`；奖励武器换 1452002 |
| `game/player.py` | `stats/ap` 字段、`recalc_vitals()`、升级 +5AP、攻防走 stats |
| `game/monster.py` | 读取 `weaponDefense` → `self.pd` |
| `game/combat.py` | 命中结算走 `stats.roll_damage`（近战与箭矢两条路径） |
| `game/inventory.py` | `stat_bonus()`（装备四维/hp/mp 词条汇总） |
| `game/save_manager.py` | v3：存 stats/ap；v2→v3 自动分配迁移 |
| `game/panels.py` | 状态窗口（原版素材 + fallback 自绘） |
| `game/game.py` | S 键开关状态窗（不与「下跳」冲突：按住空格时 S 仍下跳） |

## 7. 测试（pytest，纯函数用合成数据，不依赖 WZ）

- `test_stats.py`：加点扣减/非法属性拒绝、自动分配、HP/MP 公式、
  atk 随主属性单调增、roll_damage 上下界与怪物减伤、wear_block 五维门控
- `test_save_manager.py` 追加：v2 旧档迁移补 stats/ap（按职业自动分配）
- `test_jobs.py` 追加：奖励武器为 1452002
