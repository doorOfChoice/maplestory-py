# 职业 / 转职系统（弓箭手 1 转）设计文档

- 日期：2026-08-31
- 状态：待评审
- 范围：为 pygame 单机重制引入「职业 + 转职」框架，首个可玩职业为**弓箭手 1 转**，并实现**远程箭矢弹道**。

## 1. 背景与目标

当前项目已具备完整的单机核心循环（WZ 解析、foothold 物理、近战+技能战斗、背包/装备、任务、原版 UI、存档），但缺少职业系统：`Player.job` 恒为 0，技能却写死为战士的 `1001004/1001005`（`settings.py`），而出生点是弓箭手村。职业、技能来源、攻击方式三者互相矛盾。

本设计目标：

1. 建立**数据驱动的职业注册表**，职业/技能/图标/数值全部取自官方 WZ，不新增任何自造素材。
2. 实现**新手 → 弓箭手 1 转**的转职流程（导师 NPC + 等级门槛）。
3. 把技能系统从「写死战士树」改为「按职业树加载 + 四重门控学习」。
4. 为弓箭手实现**直线快箭 + 穿透计数**的远程弹道，与现有帧动画/特效体系一致。
5. 框架可扩展到其余职业/多转，但本轮不实现。

## 2. 范围（In / Out）

**In**
- 职业注册表（新手 0、弓箭手 3000）
- 转职：Lv10 找导师赫麗娜(1012100) 转弓箭手
- 弓箭手技能树 `300.img`（断魂箭 3001004、二连箭 3001005、buff 3001003、被动 3000000/1/2）
- 技能学习门控（SP / 职业 / 前置 req / 人物等级 CharLevel）
- 远程箭矢弹道 + `shoot1` 拉弓动画
- 动态快捷键、存档 v2、UI 职业名/技能窗

**Out（本轮不做）**
- 战士/法师/盗贼/海盗职业与各自导师
- 2 转 / 3 转分支选择
- 四维属性（STR/DEX/INT/LUK）与每级属性点分配（沿用现有 `attack_value/defense_value`）
- 弩（crossbow）专属逻辑（仅 `shoot2` pose 顺带支持）
- 怪物定时重生、商店/仓库等其它 P0 缺口

## 3. 决策记录（已与使用者确认）

| 决策点 | 选定 |
|---|---|
| 范围 | 只做弓箭手 1 转（框架可扩展） |
| 转职触发 | 把导师放进可达图（100000000 额外生成一个实例） |
| 远程弹道 | 本轮一起做，采用**直线快箭 + 穿透计数** |
| 四维属性 | 暂不做，保留简化攻防 |
| 开局身份 | 新手(job 0)，**只有 J 普攻、无任何技能**，Lv10 转职后才拿弓走远程 |
| 新手技能 | 无。`SkillBook` 只加载当前职业树，新手树为空 → 零技能 |
| 战士技能 | **不保留**。删除写死的 `1001004/1001005` 接线，无需向后兼容 |
| 转职奖励 | 送 1452000 短弓并自动装备 |
| 职业名来源 | 取自 WZ 现有文本（`String.wz`），不另写 |

## 4. WZ 数据来源（全部实测验证，无自造）

### 4.1 技能树（`Skill.wz`，按 skill id 前缀分图）
- 新手：`000.img`
- 弓箭手 1 转：`300.img` → 技能 `3000000`(被动 精準強化,invisible)、`3000001`、`3000002`、`3001003`(buff, `req={3000000:3}`, `action=alert2`)、`3001004`(断魂箭)、`3001005`(二连箭, `req={3001004:1}`)
- 单技能节点字段：`icon/iconMouseOver/iconDisabled`（内嵌 PNG）、`level/N`（每级 `mpCon`/`damage`/`bulletCount`/`mobCount`）、`req`（前置 `{id:lv}`）、`CharLevel`（学习所需人物等级）、`invisible`（职业自动附赠被动）、`hit/finalAttack/action/effect/ball`（特效/弹道帧）。
- 实测数值：`3001004` level1 = `mpCon7, damage190`；`3001005` level1 = `mpCon10, damage92, bulletCount2`。

### 4.2 技能名（`String.wz/Skill.img`）
- `3001004` → 断魂箭；`3001005` → 二连箭；含 `desc` 与 `h1..h20` 每级描述。

### 4.3 拉弓动画（`Character.wz/Weapon`）
- 弓 `1452000`（`01452000.img`）含动作 **`shoot1`**；弩 `146xxxx` 含 `shoot2`。现有 `CharacterRenderer` 已能合成任意 pose，无需新渲染代码。

### 4.4 箭矢与命中特效（`Skill.wz`）
- 飞行箭矢贴图：`300.img/skill/3001004/ball/0..2`（3 帧 canvas）。
- 命中特效：`3001004/hit/0`、`3001005/hit/0|1`。

### 4.5 导师 NPC（`Npc.wz` + `String.wz/Npc.img`）
- 赫麗娜 = NPC **1012100**，原版位于地图 100000201（不在当前 `TRAVEL_MAPS`，且无 type-2 直连门）。
- 本设计改为：在已可达的 **100000000（弓箭手村）** 额外生成一个赫麗娜实例，立绘/名字仍取自 WZ。

### 4.6 职业名（无专用 WZ 表）
- `String.wz` 中 `1000/3000` 仅有 `bookName`（技能书标题），无「职业码→职业名」表。
- 职业名字符串取自 WZ 现有文本：`弓箭手`（见 `Map.img/100000000/mapDesc`「可以轉職成為弓箭手」、`Npc.img/1012100` 对话「你想成為弓箭手嗎？」）；`新手` 同理。仅这两个名字，落在 `jobs.py` 常量中并注明 WZ 出处。

### 4.7 需修正的现有写死点
- `assets.py:800/812/816`：`skill_icon/skill_effect_frames/skill_hit_frames` 写死 `"100.img"`。
- `skills.py:44`：`load_skill_defs` 写死 `Skill/100.img`。
- `settings.py:106-107`：`SKILL_HOTKEYS/SKILL_UNLOCK_LEVEL/HOTKEY_SKILLS` 写死战士技能。

## 5. 架构与模块改动

### 5.1 新增 `game/jobs.py`（职业注册表）
```
@dataclass JobDef:
    code: int
    name: str
    tree_imgs: list[str]
    passive_ids: list[int]
    advance_lv: int
    trainer_npc: int | None
    starter_weapon: str | None

JOBS: dict[int, JobDef] = {0: 新手, 3000: 弓箭手}
```
- 新手 `tree_imgs=[]`、`passive_ids=[]`（零技能，仅 J 普攻）；弓箭手 `tree_imgs=["300.img"]`。
- `resolve_skill_img(skill_id: str) -> str`：**纯函数**，按 id 长度定图（8 位→`id[:4]+".img"`，7 位→`id[:3]+".img"`）。
- `skill_ids_for_job(assets, code) -> list[str]`：枚举职业树 `skill/*`（integration，需 WZ）。
- `can_advance(player, jobdef) -> bool`：**纯函数**（当前 job 为前置、`level>=advance_lv`、未转过）。

### 5.2 `game/skills.py`（职业驱动）
- `SkillBook(assets, job)`：载入 = **仅当前职业树**（新手 job 0 → 空，零技能；弓箭手 → `300.img`）。
- 移除现有「1 级自动赠送首个技能」逻辑（新手开局无技能）。
- `learnable()`：排除 `invisible` 被动。
- `learn(sid, player_level)` 四重门控：**SP>0 + 职业匹配 + `req`（前置技能达等级）+ `CharLevel`（人物等级）**。
- `grant_passives(job)`：转职时把 `invisible` 被动直接满级（免费）。
- 动态快捷键 `hotkeys: dict[int, str]`（键→技能 id），学新主动技能自动补位。
- `load_skill_defs` 增解析 `req`/`CharLevel`/`invisible`。

### 5.3 `game/assets.py`（去写死 + 新增取图）
- `skill_icon/skill_effect_frames/skill_hit_frames` 改用 `resolve_skill_img`。
- 新增 `skill_ball_frames(skill_id)`（读 `ball/*`）、`is_ranged_weapon(item_id)`。
- `attack_pose(equips)`：武器为弓(145xxxx)/弩(146xxxx) 时返回 `shoot1`/`shoot2`，否则维持近战 `ATTACK_POSES`。

### 5.4 `game/combat.py`（远程弹道）
- 新增 `Arrow` 实体：`{x, y, vx, vy, frames, dmg, mob_count, life, hit_ids, assets}`。
  - `update(dt, monsters)`：直线飞行（无重力），逐帧与未命中怪 `rect` 相交 → `take_hit` + 飘字 + `hit` 特效；命中数达 `mob_count` 或 `life<=0`/出界即消失。
- `Combat.spawn_arrows(player, skill_data)`：按 `bulletCount`（默认 1）生成错峰箭，速度 `facing * ARROW_SPEED`，从手部位置出发。
- `Combat.arrows: list[Arrow]`；`Combat.update_arrows(dt, monsters)`；`Combat.draw` 一并绘制箭矢。
- 近战 `player_attack` 保留（非弓职业仍用）。

### 5.5 `game/player.py`
- `job: int` 真实化。
- `advance_to(code, assets)`：改 job → 重建 `SkillBook` → `grant_passives` → 武器空则 `make_item(starter_weapon)` 并装备 → `refresh_equips` → 重排快捷键。纯状态部分拆为可测函数（如 `compute_advance_state`）。
- 新增 `is_ranged()`：job 为弓箭手且已装备弓/弩。

### 5.6 `game/game.py`
- `_spawn_life`：在 100000000 出生点附近注入赫麗娜实例（用数据 dict 造 `NPC`）。
- `_try_talk`：命中导师 → `can_advance` 真则弹转职对话框（复用 `UtilDlgEx` + BtYes/BtNo）→ 确认 `advance_to(3000)` + toast；等级不足显示进度提示。
- `_cast_skill` / 快捷键：读 `player.skills.hotkeys` 动态表；数字键 1..n。
- `_update`：每帧 `combat.update_arrows(dt, monsters)`。
- 远程起手：`Game` 在检测到一次新的远程攻击时调用 `combat.spawn_arrows(...)`（Player 不持有 Combat）。
- 欢迎文案更新。

### 5.7 `game/settings.py`
- 删除 `SKILL_HOTKEYS/SKILL_UNLOCK_LEVEL/HOTKEY_SKILLS`（`SKILL_COOLDOWN` 保留为默认回退）。
- 新增：`ARROW_SPEED`、`ARROW_LIFETIME`、`BOWMAN_JOB=3000`、`BOWMAN_STARTER_BOW="1452000"`、`BOWMAN_TRAINER_NPC="1012100"`、导师放置坐标 `TRAINER_SPAWN`。

### 5.8 `game/save_manager.py`
- `version 1 → 2`：存 `player.job` + `skills.hotkeys`。
- 迁移：v1 旧档 → `job=0`、快捷键默认。

### 5.9 UI（`panels.py` / `ui.py`）
- 技能窗按 `book.learnable()` 列出（不再读 settings 写死表）。
- 快捷栏读动态 `hotkeys`。
- 装备窗/状态区显示职业名。

## 6. 数据流（转职 + 远程一次攻击）

```
新手 Lv10 靠近赫麗娜 → Enter → can_advance 真 → 转职对话框(yes)
  → Player.advance_to(3000): job=3000, 附赠被动满级, 装备短弓, 重排快捷键
  → toast「转职成功：弓箭手」

按 1 施放断魂箭 → SkillBook.cast(3001004) 通过门控 → Player.start_attack(skill)
  → Game 检测远程起手 → Combat.spawn_arrows(player, skill) 生成 1 支 Arrow(ball 帧)
  → 每帧 Combat.update_arrows: Arrow 直线前进 → 命中怪 take_hit + hit 特效
  → 命中数达 mobCount 或超射程/寿命 → Arrow 消失
```

## 7. 测试策略（TDD，合成数据、不依赖 WZ）

遵循 `AGENTS.md`：透过公开接口、不用 mock、不用 fixture、合成数据。

| 测试文件 | 验证的 seam |
|---|---|
| `test_jobs.py` | `resolve_skill_img` 长度规则；`can_advance` 门控（等级/职业/已转） |
| `test_skill_gating.py` | 注入合成 `SkillDef`，验证 `learn` 的 SP/职业/req/CharLevel 四重门 + `grant_passives` 满级 |
| `test_advance_state.py` | `advance_to` 的纯状态部分（job 变更、被动附赠、快捷键重排） |
| `test_projectile.py` | 合成 target（暴露 `rect()/take_hit()`），验证直线命中、`mob_count` 上限、`bulletCount` 支数、超程消失 |
| WZ 冒烟（`@pytest.mark.skipif` 无 WZ） | `load_skill_defs`/`skill_ids_for_job`/`skill_ball_frames` 能解析真实树 |

## 8. 实现顺序（vertical slice，每片红→绿）

1. `resolve_skill_img` + `assets` 去写死（删除 `100.img`/战士技能接线，新手开局零技能）
2. `jobs.py` 注册表 + 纯函数 `can_advance` + 测试
3. `SkillBook` 职业驱动 + 四重门控 + 测试
4. `Player.job` / `advance_to`（纯状态部分）+ 存档 v2 迁移 + 测试
5. 导师注入 + 转职对话流程
6. `Arrow` 弹道 + `shoot1` pose + 生成接线 + 测试
7. 动态快捷键 + 技能窗/快捷栏 UI + 欢迎文案
8. WZ 冒烟测试

## 9. 风险与开放项

- **职业名无 WZ 专表**：仅 `新手/弓箭手` 两串取自 WZ 文本，落在 `jobs.py` 常量并注明出处；若后续扩职业，需为每个职业名找 WZ 出处或统一策略。
- **导师放置坐标**：需选一个 100000000 内可站立、不挡路、玩家易发现的 foothold 坐标（实现时定，可能微调）。
- **箭矢手感常量**：`ARROW_SPEED/ARROW_LIFETIME` 需实机调；先给保守默认（如 speed≈900 px/s、life≈0.6s）。
- **远程起手时机**：现有近战在攻击首帧即结算；远程应「起手生成箭、飞行中结算」，需确保一次攻击只生成一批箭（用 `attack_hit_applied` 类似的一次性标志）。
- **存档兼容**：v1→v2 迁移要保证旧档不崩、job 缺省为 0。
- **`invisible` 被动满级值**：WZ 被动 `level` 表上限（多为 20），满级取该技能 `level` 子节点数。
