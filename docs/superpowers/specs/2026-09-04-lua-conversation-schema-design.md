# Lua 声明式对话系统（通用会话 Schema）设计文档

- 日期：2026-09-04
- 状态：待评审
- 范围：为 NPC 对话建立**一套统一的声明式 schema**：任何 NPC 对话 = 若干步骤，每步 = 黑文本行 + 蓝字交互行（+可选 yes/no 按钮），点击触发 Lua 函数式动作并跳转，直至结束。转职、任务接取/交付、出租车菜单全部收编到同一解释器，Python 不再持有任何对话状态机与文案。

## 1. 背景与问题诊断

当前 NPC 对话由三套互不相通的机制拼成（见 `src/game/npc_dialogue.py`）：

1. **固定槽位式**：`npc/*.lua` 的 `entries()` 把任务翻译成 `QuestDef`，对话文本只有
   `accept_lines / accept_yes / accept_no / complete_lines / complete_yes / complete_stop`
   六个槽；状态机（offer→accepted / complete→completed / status）写死在 Python
   `_quest_button`（`npc_dialogue.py:340`），加一步对话就得不改 Python。
2. **命令式会话式**：`advance.lua` 的 `new/snapshot/choose/done` 模型，灵活但作者要手写
   if-elseif 状态机；且它是特例通道（`_begin_lua_quest/_advance_button`），只服务转职。
3. **蓝字交互硬编码**：可点击蓝字只存在于 `show_quest_list` 的多任务菜单，条目类型
   （quest/teleport）由 Python 分流写死，新增一种点击行为必须改 Python。

缺口：没有「一步 = 黑文本 + 任意蓝字 + 任意动作 + 跳转/结束标记」的统一原语，也没有
步骤/链接级的运行时条件显隐（现有 `ctx` 在启动期为 nil，`entries()` 完全静态）。

## 2. 范围（In / Out）

**In**
- 新 Lua 契约 `talk(ctx)`：声明式步骤图 + 函数式 show/click
- 通用对话解释器 `src/game/systems/conversation.py`
- `npc_dialogue.py` 路由统一：转职 / 官方任务 / 自定义任务 / 出租车菜单全部收编，删除
  `_quest_flow`、`_advance_session`、`_menu_items` 三套并行状态
- Say 槽位适配器：`QuestDef` 的对话文本折成同样的步骤结构（Python 构造，源不再重要）
- UI：`show_quest` 与 `show_quest_list` 合并为单一渲染契约（黑文本与蓝字可同面板共存）
- 宿主函数扩展：`teleport(map_id)`；`ctx` 实时视图
- 重写 `advance.lua` 与示例 `npc/*.lua`；更新 `resources/content/AGENTS.md`
- 单测（合成 Lua 源码字符串，不依赖 WZ）

**Out（本轮不做）**
- 内联蓝字标记（`#L..#l` 嵌句内渲染）；官方 Say 中此类文本按「拆行」近似
- 商店面板对话化（商店仍是面板，对话只提供「商店」链接入口）
- 协程式线性剧本（方案 C，被否：跨帧驻留与存档语义过重）
- `QuestLog` 状态机、任务条件判定、奖励发放逻辑的改动（原样复用）

## 3. 决策记录（已与使用者确认）

| 决策点 | 选定 |
|---|---|
| 统一范围 | **全部统一**：转职/任务接交/出租车/寒暄之外的对话路径都走新解释器 |
| 蓝字排版 | **块级蓝字行**（黑文本在上、蓝字列表在下），不做内联 `#L..#l` |
| 条件/动作表达 | **Lua 函数式**：`show = function(ctx)`、`click = function(ctx)`，动作集合对 Python 零封闭 |
| 契约结构 | **方案 A 步骤图解释器**（否 B「升级 snapshot/choose」：样板不消失；否 C「协程剧本」：过度设计） |
| yes/no 按钮 | 保留为步骤级 `buttons` 糖（转职确认等原版按钮样式），其余一律蓝字 |

## 4. Lua 契约

`npc/<npc_id>.lua` 在现有 `entries()` / `shops()` 之外新增导出（可选）：

```lua
function M.talk(ctx)            -- 每次开对话实时调用，返回会话定义
  return {
    title = "托德",              -- 面板标题；缺省用 NPC 名
    start = "greet",            -- 起始步名
    steps = {
      greet = {
        text = { "哟，冒险者。要点什么？" },   -- 黑文本行；或 function(ctx) 返回数组
        links = {
          { label = "接任务：收集蓝药水",       -- 或 function(ctx) 返回 string
            show  = function(ctx) return quest_state("c_1012119_1") == "available" end,
            click = function(ctx) accept_quest("c_1012119_1"); return "after_accept" end },
          { label = "传送：射手村",
            show  = function(ctx) return ctx.player.map ~= 100000000 end,
            click = function(ctx) teleport("100000000") end },   -- 返回 nil = 结束
        },
        buttons = { yes = "hire", no = "refuse" },  -- 可选糖：BtYes/BtNo → 跳步
      },
      after_accept = { text = { "按 Q 查看任务日志。" } },  -- 无 links/buttons = 终态
    },
  }
end
```

### 4.1 步骤（step）字段

| 字段 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `text` | 数组[string] 或 function(ctx) | 空 | 黑文本行，按序渲染；支持官方标记（`#t#o#m#p`、`#b/#r/#k`、`\n`，走现有 `render_markup`） |
| `links` | 数组[link] | 空 | 蓝字交互行，按序渲染 |
| `buttons` | 表 `{yes=步名, no=步名}` | 无 | 渲染 BtYes/BtNo（回车=确认键、Esc=取消键，同现有映射）；某键缺省则不画 |
| `next` | string | 无 | 终态「确定」后的跳转；缺省 = 结束对话 |

### 4.2 链接（link）字段

| 字段 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `label` | string 或 function(ctx) | 必填 | 蓝字文本（可含标记） |
| `show` | function(ctx) → boolean | 恒显示 | 渲染前调用，false 则整行隐藏、不占命中区 |
| `click` | function(ctx) → string/nil | 结束 | 先执行副作用（宿主函数），返回步名跳转；返回 nil/false = 结束对话 |

### 4.3 结束标记

隐式即可：**无 links 且无 buttons 的步骤 = 终态**（画 BtOK，按下结束）；任何 `click`
返回 nil 也立即结束。不设显式 `end` 字段，减少作者心智负担。

### 4.4 会话生命周期

非模态。以下任一情况会话销毁（与现有 `update()/close_all()` 行为一致）：
玩家走远超过 `TALK_RANGE`、Esc 关闭（有 `buttons.no` 时走 no 分支，否则直接结束）、
切图、重生。解释器不持久化：每次 `try_talk` 重新调 `talk(ctx)` 建模——所有条件天然是「此刻」的。

## 5. 解释器：`src/game/systems/conversation.py`

公开 seam（单测入口）：

```python
Conversation.from_source(lua_src: str, env: Mapping[str, Callable],
                         ctx_view: dict, title: str) -> Conversation
Conversation.current() -> Snapshot      # 渲染快照（纯数据）
Conversation.click_link(i: int) -> None # 调第 i 个可见链接的 click，按返回值跳转/结束
Conversation.press(key: str) -> None    # "confirm"/"close"/"ok" → buttons 路由
Conversation.done -> bool
```

- `Snapshot = {title, lines: [str], links: [str], buttons: [str], terminal: bool}`，
  由 UI 层消费；`show` 过滤与 `label/text` 求值都在 `current()` 完成。
- 沙箱沿用 `scripting.py` 的 `_sandboxed_runtime()`（禁 os/io/package/debug/dofile/loadfile）。
- 加载时把 Lua 步骤图**整体折成 Python 结构**（步名字符串、文本行列表已求值一次；
  `text/label/show/click` 为 function 的保留 lupa 引用，在 `current()/click` 时调用），
  避免每帧穿 Lua 遍历。
- `scripting.LuaSession`（snapshot/choose 契约）随 `advance.lua` 重写后删除；
  `script_api.make_globals` 原样复用并扩展。

### 5.1 ctx 实时视图

每次开对话与每次求值重建，纯数据（不传真实对象进沙箱）：

| 路径 | 类型 | 说明 |
|---|---|---|
| `ctx.player.level` / `.job` | number | 现有字段 |
| `ctx.player.map` | number | 当前地图 id（新增，出租车按图过滤用） |
| `ctx.npc.id` / `ctx.npc.name` | string | 当前 NPC（`npc_name` 旧字段并入） |
| `ctx.jobdef.code/.name/.advance_lv` | 现有 | 仅转职任务会话携带 |

### 5.2 宿主函数（`script_api.make_globals` 扩展）

| 函数 | 新增/保留 | 说明 |
|---|---|---|
| `teleport(map_id)` | 新增 | 记录切图请求（解释器结束会话后由宿主执行 `Game._enter_map`），Lua 侧无需再返回特殊值 |
| `accept_quest` / `complete_quest` / `quest_state` / `quest_available` / `quest_completable` / `quest_info` | 保留 | 现注册条件不变（携带 world/quest_defs） |
| `give_reward` / `can_advance` / `advance_job` / 商店三函数 | 保留 | 不变 |

`advance_job()` 行为扩展：置 `ctx.advanced` 的现有机制保留，宿主在会话结束时若
`advanced` 为真则播音效 + `force_complete(adv_* qid)`（与现状一致）。

### 5.3 错误处理

| 位置 | 行为 |
|---|---|
| `talk()` 加载/调用抛错 | 整个会话弃用，回落下一优先级（合成默认会话或寒暄），logging.warning |
| 单个 `show` 抛错 | 该链接隐藏并 warning，其余正常 |
| `click` 抛错 | 结束会话并 warning（宁可关窗不可卡死），游戏状态以已发生的宿主副作用为准 |
| 步名不存在（click 返回错误名字） | 结束会话并 warning |

单脚本失败隔离原则不变：一个 NPC 的脚本坏了不影响其它 NPC。

## 6. 收编现有路径

### 6.1 `npc_dialogue.try_talk` 统一路由链

1. NPC 有 `talk()` → 开 Lua 会话；
2. 否则该 NPC 有任务（`collect_npc_quests` 非空）或传送目的地或转职任务 →
   开**合成默认会话**（见 6.2）；任务链接点进去 = 任务子会话（见 6.3）。
   取消现 `len(qlist)==1` 的「单任务直开 offer」特判：哪怕只有一条链接也显示菜单，
   少一条分叉、行为可预期；
3. 有商店且以上皆空 → 直接开店（现状保留）；
4. 其余 → 寒暄气泡（现状保留，含 storage 按钮）。

删除的状态：`_quest_flow`、`_advance_session/_advance_ctx/_advance_npc/_advance_qid`、
`_menu_items/_menu_npc` 全部收拢为单个 `self._conv: Optional[Conversation]`。

### 6.2 合成默认会话（吸收选择菜单 + 出租车）

Python 构造（不经 Lua）一个标准步骤图：
- `greet` 步：黑文本为空；标题沿用现状（出租车且无任务时「<NPC 名> · 要去哪里？」），
  links = 可交付任务在前、可接任务、传送目的地（按 `ctx.player.map` 剔除当前图，
  复用 `travel.teleports_of`）、有商店则加「商店」链接；
- 任务链接 `click`：不直接调 accept，也**不**在解释器里嵌套子会话——点击后由
  `npc_dialogue` 关闭当前会话、打开该任务的子会话（6.3）。对用户等价，
  且解释器零新概念。商店链接同理：关闭会话、打开商店面板。

### 6.3 任务子会话适配器（官方与自定义任务共用）

`QuestDef` 现有 Say 槽位折成同一结构，副作用逻辑复用 `QuestLog.accept/complete`：
- offer 步：`accept_lines`（缺省生成「要接受任务…」）+ `buttons={yes, no}`；
  yes → `accept()` 成功进 accepted 步（`accept_yes`）、失败直接关；no → declined 步（`accept_no`）；
- complete 步：`complete_lines` + `buttons={yes, no}`；yes → `complete()` 成功进
  completed 步（`complete_yes`）、失败（条件未满足）进 stop 步（`complete_stop`）；
- 进行中来找（现 status 提示）：单步 `complete_stop`，终态。

`next_quest/灯泡/存档` 均不受影响——改的只是「对话怎么走」，不是「任务怎么算」。

### 6.4 转职

`content/advance.lua` 重写为 `talk(ctx)` 步骤图：
`weak`（等级不足，终态）/ `confirm`（buttons yes/no）/ `advanced`（终态）/
`declined`（终态）；`adv_*` QuestDef 的 `script="advance"` 字段含义改为「NPC 会话来自
该脚本」，由 6.1 的路由使用。`test_lua_advance.py` 改为驱动新解释器断言步骤图。

## 7. UI 改动（`src/game/render/ui.py`）

- 新契约 `show_conv(title, lines, links, buttons, terminal)` 取代 `show_quest` +
  `show_quest_list`：黑文本与蓝字**同面板共存**（现两态互斥）；
- 蓝字行复用现有 UtilDlgEx 列表画法（悬停高亮 `QUEST_LIST_BLUE*`、行命中区
  `quest_entry_rects`），行右侧 Lv 标注保留（任务链接可用）；
- 按钮区：`buttons` 非空画 BtYes/BtNo；终态画 BtOK；两者皆无则只有蓝字（无按钮）；
- `quest_hit/quest_list_hit` 合并为 `conv_link_hit(pos) -> int|None` 与
  `conv_button_hit(pos) -> str|None`；
- 布局：面板高度 = 标题 + 黑文本行 + 蓝字行 + 底部按钮，沿用 `_dlg_frame` 三段拼贴。

## 8. 迁移顺序（vertical slice，每片测试绿灯再下一片）

1. **解释器 + `show_conv`**：新代码 + 合成对话单测；旧路径原样并存。
2. **任务子会话适配**：官方/自定义任务接交走解释器；删 `_quest_flow/_quest_button`。
3. **合成默认会话**：吸收选择菜单与出租车；删 `_open_choice_menu/_menu_items`。
4. **advance.lua 重写**：删 `_advance_session` 全家与 `scripting.LuaSession`。
5. **内容脚本迁移**：`npc/*.lua` 逐个补 `talk()`（1012119 商店+任务示例、1012100 等
   出租车、reward_test），更新 `resources/content/AGENTS.md`。

## 9. 测试策略（pytest，公开 seam，无 mock/fixture，合成数据不依赖 WZ）

| 文件 | 覆盖 |
|---|---|
| `test_conversation.py`（新） | `Conversation.from_source` 吃内嵌 Lua 字符串：show 过滤、click 跳步、返回 nil 结束、buttons 路由、回车/Esc 映射、text/label 函数式、步名不存在与 click 抛错→done |
| `test_quest_conversation.py`（新） | Say 槽位适配器：offer/complete/status 各分支快照与副作用（accept 成功/失败、complete 条件不足→stop） |
| `test_taxi.py` / `test_npc_quests.py` / `test_quest_list.py`（改） | 断言合成默认会话的链接顺序（可交付在前）、按当前图剔除、商店链接出现条件 |
| `test_lua_advance.py`（改） | 新 schema 转职步骤图端到端（合成 player/jobdef，无 WZ） |

## 10. 文档

- `resources/content/AGENTS.md`：`talk(ctx)` 契约、step/link 字段表、结束标记、示例、
  固定槽位（`accept_lines` 等）降级为「不写 `talk()` 时的默认文本」。
- 根 `AGENTS.md` 架构要点补一句：对话统一走 `conversation.py` 解释器。
