# AGENTS.md — NPC 对话/任务规则脚本（content/）

本目录是「规则引擎文本」的家：每个 NPC 的对话/任务流程用 **Lua** 写成一份脚本。
**改台词、改分支、给不同 NPC 定义不同任务，只改本目录的 `.lua`；不碰 Python。**
Python 层（`src/game/systems/scripting.py` + `src/game/systems/script_api.py`）负责把上下文
灌进来、执行 Lua、并把 `snapshot()` 回报的内容渲染到原版 UI。

## 文件与命名

- 一个场景/一份脚本 = 一个 `.lua` 文件，按用途命名：`advance.lua`（转职）、
  `npc/<npc_id>.lua`（后续每个 NPC 一份，如 `npc/1012100.lua`）。
- 脚本是 Lua **模块**：最后必须 `return M`（一个导出工厂的表）。
- 沙箱运行时通过 `scripting.build_lua_session("advance", ...)` 加载
  `resources/content/advance.lua`；文件名即脚本名，不含 `.lua` 后缀。
- **不要**在 `.lua` 里 `import` / `require` 任何游戏模块；沙箱已禁用 `package`。

## 沙箱环境

- 脚本只能看到 Lua 标准库里的**纯计算**库：`string`、`table`、`math`，
  `setmetatable`、`pairs`、`ipairs`、`tonumber`、`tostring` 等。
- **禁用**：`os`、`io`、`package`、`debug`、`dofile`、`loadfile`、`eval` —
  因此不能读文件、不能执行系统命令、不能动态加载代码。
- 内容为仓库内可信文本，故沙箱无需额外防护；但仍请遵守上面的限制。

## 每份脚本必须导出的契约

宿主把模块加载后调用 `mod.new(ctx)` 得到一台会话，之后反复调用：

```
new(ctx)                       → 会话表（记录状态，返回 self）
session:snapshot()             → 当前该显示什么（纯数据表）
session:choose(label)          → 一次按钮/按键选择，推进状态
session.done                   → bool，会话是否结束（终态置 true）
```

要点：
- 用 **冒号方法** 定义 `snapshot` / `choose`（`function M:snapshot()`），因为它们
  需要读 `self`。宿主以 `session["snapshot"](self.session)` 方式调用。
- `new` 用**点方法**（`function M.new(ctx)`），宿主以 `mod["new"](ctx)` 调用。
- `choose(label)` 里，但凡对话**已经结束**，就必须 `self.done = true`；否则
  游戏会把当前画面一直渲染下去。

## snapshot() 返回表字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `npc` | string | 说话人名字（一般取 `self.ctx.npc_name`） |
| `lines` | 数组[string] | 本次要显示的文本行，按顺序渲染 |
| `mode` | string | UI 组件：`"quest"`（任务/确认框）、`"dialog"`（寒暄气泡）、`"menu"`（多任务列表）。当前转职路径始终以 `"quest"` 渲染 |
| `options` | 数组[string] | 可选按钮标签。为空 = 终态陈述（按「确定」结束） |

> 数组自动从 Lua 的 1 起始索引折成 Python 数组；数组里是字符串标签。

## 可读变量 ctx（只读视图，Lua 读到标量/嵌套表，不持有真实对象）

宿主把真实上下文转成只读表 `ctx`，当前暴露：

| 路径 | 类型 | 含义 / 值域 |
|---|---|---|
| `ctx.player.level` | number | 玩家等级 |
| `ctx.player.job` | number | 职业代码（`0`=新手、`3000`=弓箭手...） |
| `ctx.jobdef.code` | number | 目标职业代码 |
| `ctx.jobdef.name` | string | 目标职业名（如 `弓箭手`） |
| `ctx.jobdef.advance_lv` | number | 转职所需等级 |
| `ctx.npc_name` | string | 当前 NPC 名字 |

## 可调用的全局函数（副作用在宿主侧执行）

函数由宿主注册到运行时，Lua 直接按名调用。**参数传基本类型（string/number/boolean），
不要传 ctx 表进宿主函数**。

### 转职（所有内容脚本都有）
| 函数 | 返回 | 副作用 |
|---|---|---|
| `can_advance()` | boolean | 无。判定当前玩家能否转职为 `ctx.jobdef` |
| `advance_job()` | nil | 改真身职业（附技能/武器），并置宿主 `ctx.advanced = true` |

### 任务（仅当宿主 ctx 携带 `world` / `quest_defs` 时才注册）
> 目前 `advance.lua` 的宿主上下文**没有**这两者，故下述任务函数在转职脚本里**不存在**；
> 给 NPC 写任务脚本时，宿主会传相关上下文，届时可用。

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `quest_available(npc_id)` | number/string | 数组[{qid,title,level,state}] | 该 NPC 可接取 + 可交付的任务 |
| `quest_completable(npc_id)` | number/string | 数组[{qid,title,level,state}] | 仅可交付的任务（state=`complete`） |
| `quest_state(qid)` | number/string | string | `"available"/"accepted"/"completed"` |
| `accept_quest(qid)` | number/string | boolean | 接取任务（成功 true；条件不足 false） |
| `complete_quest(qid)` | number/string | boolean | 完成任务并**发奖励**（exp/金币/物品）；失败 false |
| `quest_info(qid)` | number/string | 表{name,reward_exp,reward_money} | 任务奖励/名称信息，可拼进发奖文案 |

返回的 task 数组元素是表：`{ qid=string, title=string, level=number, state=string }`。

## 选项标签约定（重要）

宿主按钮路由把「回车/空格」映射为 `yes`、把「Esc」映射为 `no`，其余按标签直传；
当没有更匹配项时统一回落到 `ok`。因此：

- **选择型状态**：`options = { "yes", "no" }`。
- **陈述/终态**：`options = {}`（空）或 `{ "ok" }`。
- 终态时：`choose("yes"|"no"|"ok"|...)` 只要代表「确定/结束」就应 `self.done = true`。

转职流程示范（confirm「yes」→ advanced「恭喜」，advanced「ok」才结束）：
```lua
function M:choose(label)
  if self.state == "confirm" and label == "yes" then
    advance_job()              -- 改真身；不要在此时置 done
    self.state = "advanced"
    return
  elseif self.state == "confirm" and label == "no" then
    self.state = "declined"
    return
  end
  self.done = true             -- 其余（含 advanced 的 ok）一律结束
end
```

## 编写规范

- 语言：文件内注释用简体中文；每个状态对应 `snapshot()` 的一个分支。
- 用 `setmetatable({}, { __index = M })` 建会话表，把 `self.ctx`、`self.state`、
  `self.done` 存在 `self` 上。
- 需要插值/格式化用 Lua 字符串拼接 `..` 或 `string.format("（当前 Lv%d...）", ...)`。
- 一个状态一个 `lines` 数组；语义要拆分就多写几行。
- 文案数字/奖励等**数值不要写死在 Lua**——任务数值在任务数据表，脚本只通过
  `quest_info`/`ctx` 取。
- 改完可用 `uv run python -m game.main` 进游戏试；或跑单测
  `uv run pytest src/tests/test_lua_advance.py`（转职脚本路径）。
- 新增 `.lua` 后，宿主调用侧需传对应的 `build_lua_session("<脚本名>", ...)`；
  脚本名要一致。

## 参照实现

本目录 `advance.lua` 是一份可运行的完整示例（转职会话）：

- `new`：按 `ctx.player.job` / `can_advance()` 决定入口状态。
- `snapshot`：按 `self.state` 返回 `{npc,lines,mode,options}`。
- `choose`：`confirm` 时 yes/no 分别转 `advanced`/`declined`；其余置 `done = true`。

新增 NPC 脚本或自定义任务时，照此结构复制一份，改状态机与文案即可。
