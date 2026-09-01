# Lua 自定义任务系统（任意 NPC 多任务）设计文档

- 日期：2026-09-01
- 状态：待评审
- 范围：让内容层（`resources/content/npc/*.lua`）可为**任意 NPC** 定义**多个自定义任务**并接入游戏流程；任务状态追踪复用现有 `QuestLog`，官方任务与自定义任务可共存于同一 NPC 的接取列表。

## 1. 背景与目标

当前 Lua 系统只承担转职对话（`advance.lua`，`src/game/npc_dialogue.py:238` 唯一调用点），任务定义全部来自 `Quest.wz`（`load_quest_defs`），任务状态由 `QuestLog` 管理且随存档保存。`script_api.py` 已备好 `give_reward` / 任务 CRUD 等全局函数，但因 `build_lua_session` 调用未传 `world`/`quest_defs` 而注册不上（`src/game/systems/script_api.py:42-66`）。

目标：**给任意 NPC 定义自定义任务，接入现有任务流程**——接取/完成/进度/存档/头顶灯泡/多任务列表全部复用现有机制，不重写状态机。

## 2. 范围（In / Out）

**In**
- `resources/content/npc/<npc_id>.lua` 定义多任务（条件 / 奖励 / 对话文本）
- Python 侧新增加载器：Lua 任务定义 → `QuestDef` → 合并进 `quest_defs`
- 官方任务与自定义任务在同一 NPC 下**共存**于接取列表
- 任务状态 / 存档 / NPC 头顶灯泡等现有机制对自定义任务自动生效
- 单测（合成数据、不依赖 WZ）

**Out（本轮不做）**
- Lua 自定义任务之外的状态机改写（`QuestLog` 不动）
- 自定义寒暄 `greet(ctx)`（预留字段，本轮不接入）
- Lua 驱动的复杂任务分支（非标准 offer/complete/status 流程）
- `advance.lua` 转职流程的改造

## 3. 决策记录（已与使用者确认）

| 决策点 | 选定 |
|---|---|
| 任务状态归属 | **方案 A**：Lua 只定义 + 翻译成 `QuestDef`，状态追踪复用 `QuestLog` |
| 任务类型 | 标准任务条件（击杀 / 收集 / 等级 / 前置等 `QuestDef` 既有字段） |
| 脚本组织 | `content/npc/<npc_id>.lua`，每 NPC 一份 |
| 官方+自定义共存 | 是，合并进同一 `quest_defs` 后由 `collect_npc_quests` 自然筛选 |
| qid 命名空间 | 自定义任务 id 加前缀 `c_`，避免与 WZ 数值 id 冲突 |
| 接入点 | 只改 `game.py._build_world` 一处合并；NPC 路由 / 状态机 / 存档零改动 |

## 4. 架构与模块改动

### 4.1 新增 `src/game/systems/lua_quests.py`

- `load_lua_quest_defs(assets, ctx=None) -> Dict[str, QuestDef]`：
  - 扫描 `resources/content/npc/*.lua`（文件名即 `npc_id`）
  - 用现有 `scripting._sandboxed_runtime()` 沙箱加载每个脚本，调用 `mod.quests(ctx)` 取任务数组
  - `ctx` 为只读视图（与 `scripting._ctx_view` 一致：`{player: {level, job}}`），用于脚本按玩家状态做条件判断；传 `None` 时置空
  - 把每个任务字典翻译成 `QuestDef`（字段映射见下），`start_npc`/`end_npc` 缺省取脚本所在文件名
  - 任务 id 加 `c_` 前缀：`"c_<npc_id>_<idx>"`（若脚本内显式 qid，仍强制前缀以防覆盖 WZ 任务）
  - 翻译失败（字段类型不符合预期、必需字段缺失）的单条任务跳过并用 `logging.warning` 记录，不拖垮其余任务
- 任务字典字段映射（对齐 `QuestDef`，`src/game/systems/quests.py:88-123`）：
  - 条件：`lvmin` `lvmax` `jobs` `start_items`（接取需持有）`prereq`（前置任务）`kills` `end_items`（完成需收集）
  - 奖励：`accept_items` `reward_exp` `reward_money` `reward_items`（负数=收回）
  - 对话：`accept_lines` `accept_yes` `accept_no` `complete_lines` `complete_yes` `complete_stop`
  - 可选：`next_quest` `parent` `order` `area` `desc0/1/2`
- `script_api.make_globals` 的 `give_reward` / 任务 CRUD 逻辑**不加到本模块**：自定义任务奖励走 `QuestDef` 奖励字段由 `QuestLog.complete` 发放（与官方任务同一路径），不经过 `give_reward`。

### 4.2 修改 `src/game/game.py`

- `_build_world()`（`src/game/game.py:95-109`）中，WZ 任务加载完成后合并：
  ```python
  self.quest_defs = {**quest_box.get("defs") or {}, **load_lua_quest_defs(self.assets)}
  ```
- 其余（`NpcDialogueController`、`_npc_marker`、`_quest_extra_goal_lines`、存档）均读 `self.quest_defs`，无需改动。

### 4.3 Lua 脚本契约（`content/npc/<npc_id>.lua`）

```lua
local M = {}

function M.quests(ctx)
  return {
    {
      name = "红药水收集",
      lvmin = 1,
      end_items = {{2000000, 3}},   -- 收集 3 个红药水
      kills = {{100, 5}},           -- 杀 5 只绿蜗牛
      reward_exp = 100,
      reward_money = 500,
      reward_items = {{2000000, 2}},
      accept_lines = {"要接受红药水收集任务吗？"},
      accept_yes = {"已接受！去收集 3 个红药水吧。"},
      accept_no = {"好吧，改变心意再来。"},
      complete_lines = {"你收集够了！要领取奖励吗？"},
      complete_yes = {"奖励已发放！"},
      complete_stop = {"还差一些，继续加油。"},
    },
    -- 可再写第二个任务...
  }
end

return M
```

- `start_npc`/`end_npc` 由**文件名**决定，脚本内不必写；需要「接 NPC A、交给 NPC B」时可显式覆盖。
- 对话文本支持现有 `render_markup` 标记（`#t#` 物品名、`#o#` 怪物名等）。

## 5. 数据流

```
content/npc/<npc_id>.lua → load_lua_quest_defs() → {qid: QuestDef}（c_ 前缀）
  → game._build_world 合并 → self.quest_defs（WZ 任务 + 自定义任务）
  → Player.QuestLog(defs) 状态机 / 存档
  → NpcDialogueController.try_talk → collect_npc_quests 找到官方+自定义任务
  → 多任务列表 / 单任务接取 / 完成 / 进度提示（现有流程，零改动）
  → game._npc_marker 头顶灯泡（自动含自定义任务）
```

## 6. 测试策略（TDD，合成数据、不依赖 WZ）

| 测试文件 | 验证的 seam |
|---|---|
| `test_lua_quest_defs.py` | 用临时 `content/npc/*.lua`（monkeypatch 脚本目录）加载：`quests()` → `QuestDef` 翻译正确、`c_` 前缀、多任务、失败单条跳过 |
| `test_lua_quest_integration.py` | 合并进 `QuestLog` 后：接取 / 击杀计数 / 收集 / 完成发奖 / `collect_npc_quests` 与官方任务**共存**于列表 |

- 沙箱运行时 / 脚本目录均可注入（`load_lua_quest_defs` 暴露 `script_dir` 与 `runtime_factory` 参数，测试传临时目录）。
- 不依赖 WZ；若现有整合测试已构造 `QuestLog`，直接复用其辅助建构。

## 7. 实现顺序（vertical slice，每片红→绿）

1. `lua_quests.py` 翻译核心：`quests()` → `QuestDef`（含 `c_` 前缀、字段映射）+ 测试
2. 加载器：目录扫描 + 沙箱 + 失败隔离 + 测试
3. `game.py` 合并接线 + 整合测试（与官方任务共存于 `collect_npc_quests`）
4. 写一份示例 `content/npc/1012119.lua`（商店 NPC）冒烟验证
5. `resources/content/AGENTS.md` 补充自定义任务编写规范

## 8. 风险与开放项

- **文件名 = NPC id**：若同一文件想定义多个 NPC 的任务，本轮不支持（按用途分文件即可）。
- **`give_reward` 不参与自定义任务**：奖励统一走 `QuestDef.reward_*`，避免两套发奖路径并存；`give_reward` 保留给未来的纯脚本流程（如一次性事件）。
- **翻译失败静默**：单条任务坏不影响其它任务；坏任务在启动日志记录。
- **qid 冲突**：`c_` 前缀可避免与数值 id 撞；若脚本显式指定 qid，加载器强制加前缀以防覆盖 WZ 任务。
