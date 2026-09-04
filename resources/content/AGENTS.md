# AGENTS.md — NPC 对话/任务规则脚本（content/）

本目录是「规则引擎文本」的家：NPC 的对话流程与任务数值用 **Lua** 写成脚本。
**改台词、改分支、给不同 NPC 定义不同任务，只改本目录的 `.lua`；不碰 Python。**
Python 层负责装载与执行：`src/game/systems/conversation.py`（步骤图解释器，编译
`talk()`）、`src/game/systems/script_api.py`（注册宿主全局函数）、
`src/game/systems/lua_quests.py`（启动期扫描 `entries()`/`shops()` 翻译成任务与商店）、
`src/game/npc_dialogue.py`（路由：talk() 脚本 > 默认会话 > 直开商店 > 寒暄）。

## 文件与命名

- 一个场景/一份脚本 = 一个 `.lua` 文件，按用途命名：`advance.lua`（转职会话）、
  `npc/<npc_id>.lua`（每个 NPC 一份：任务/传送条目、商店定义、可选 `talk()`）。
- 脚本是 Lua **模块**：最后必须 `return M`（一张导出表）。
- 「脚本名」即相对 `content/` 的路径（不含 `.lua`）：`advance`、`npc/1012119`。
  转职任务（`adv_*`）以 `QuestDef.script = "advance"` 指到 `content/advance.lua`。
- **不要**在 `.lua` 里 `import` / `require` 任何游戏模块；沙箱已禁用 `package`。

## 沙箱环境

- 脚本只能看到 Lua 标准库里的**纯计算**部分：`string`、`table`、`math`，
  `setmetatable`、`pairs`、`ipairs`、`tonumber`、`tostring` 等。
- **禁用**：`os`、`io`、`package`、`debug`、`dofile`、`loadfile` —
  不能读文件、不能执行系统命令、不能动态加载代码。
- 内容为仓库内可信文本，故沙箱无需额外防护；但仍请遵守上面的限制。

## talk(ctx) 契约（对话步骤图）

NPC 对话 = 一张**步骤图**。`npc/<npc_id>.lua`（或转职脚本）可选导出 `talk(ctx)`：
每次与玩家开对话时**实时调用一次**，返回会话定义表：

```lua
function M.talk(ctx)
  local QID = "c_1012119_1"
  return {
    title = "托德",                      -- 面板标题；缺省用 NPC 名
    start = "greet",                     -- 起始步名；缺省用 steps 的第一项
    steps = {
      greet = {
        text = { "哟，冒险者。要点什么？" },
        links = {
          { label = "接任务：收集红药水",
            show  = function(c) return quest_state(QID) == "available" end,
            click = function(c) if accept_quest(QID) then return "accepted" end
                                 return "busy" end },
          { label = "交付：收集红药水",
            show  = function(c) return quest_state(QID) == "accepted"
                                      and #quest_completable(c.npc.id) > 0 end,
            click = function(c) if complete_quest(QID) then return "rewarded" end
                                 return "not_yet" end },
          { label = "随便聊聊", click = function(c) return "chat" end },
        },
      },
      accepted = { text = { "太好了！收集 10 个红药水就来找我吧。",
                           "按 Q 查看任务日志。" } },   -- 无 links/buttons = 终态
      rewarded = { text = { "这是你的奖励！" } },
      not_yet  = { text = { "还差一些，继续加油！" } },
      busy     = { text = { "现在好像接不了，回头再看看你的等级吧。" } },
      chat     = { text = { "呵呵，看你装备渐佳，是个人物。" } },
    },
  }
end
```

参考实现：`npc/1012119.lua`（任务链接显隐）与 `advance.lua`（buttons 确认流）。

### 会话定义字段

| 字段 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `title` | string | NPC 名 | 面板标题 |
| `start` | string | `steps` 首项 | 起始步名 |
| `steps` | 表/string→step | **必填** | 步骤集合；缺 `steps` 视为脚本错误 |

### 步骤（step）字段

| 字段 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `text` | 数组[string] 或 function(ctx)→数组 | 空 | 黑文本行，按序渲染。函数式文本**惰性求值**：每次刷新面板（含点击之后）重新调用，可读到最新副作用结果 |
| `links` | 数组[link] | 空 | 蓝字交互行，按序渲染 |
| `buttons` | 表 `{yes=目标, no=目标}` | 无 | 渲染 BtYes/BtNo；目标为**步名字符串**或 **function(ctx)**（先执行副作用，返回步名或 `nil`=结束） |
| `next` | string | 无 | 终态按「确定」后的跳转步名；缺省 = 结束对话 |

### 链接（link）字段

| 字段 | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `label` | string 或 function(ctx)→string | 必填 | 蓝字文本。函数式 label 在**开会话时求值一次**（不随后续刷新重算） |
| `note` | number | 0 | 行右侧 `Lv n` 灰标注；0 不画 |
| `show` | function(ctx)→boolean | 恒显示 | 渲染前调用；false 整行隐藏、**不占点击序号** |
| `click` | function(ctx)→string/nil | 结束 | 先执行副作用（宿主函数），返回步名跳转；返回 `nil` = 结束对话 |

### 结束标记（隐式）

- **无 `links` 且无 `buttons` 的步骤 = 终态**：画 BtOK，按确定/回车走 `next`（缺省结束）。
- 任何 `click` / 按钮函数返回 `nil` → 立即结束。不设显式 `end` 字段。

### 按键与鼠标路由

- 回车/空格 = `confirm`：有 `buttons.yes` 触发 yes；终态则等同按 BtOK。
- Esc = `close`：有 `buttons.no` 走 no 分支，否则直接结束。
- 点面板外 → 收起会话；走远（>140px）、切图、重生 → 会话销毁。

### 运行时语义

- 解释器**不持久化**：每次开对话重新调 `talk(ctx)` 建模，所有 `show` 条件天然是
  「此刻」的；点击链接前也会重新求值一遍可见性。
- `text`/`label` 由宿主统一做官方标记解析（`render_markup`）：`#t<id>#` 物品名、
  `#o<id>#` 怪物名、`#m<id>#` 地图名、`#p<id>#` NPC 名、`#b/#r/#k` 颜色、`\n` 换行。
  多段文本仍建议写成多个数组元素。

### 错误处理

| 位置 | 行为 |
|---|---|
| `talk()` 加载/调用抛错、缺 `talk`/`steps`、返回 `nil` | 整个会话弃用，回落下一优先级（默认会话或寒暄），记 warning |
| 单个 `show` 抛错 | 仅该链接隐藏，其余正常，记 warning |
| `click` / 按钮函数抛错 | 结束会话，记 warning（已发生的宿主副作用保留） |
| click 返回不存在的步名 | 结束会话，记 warning |

单脚本失败隔离：一个 NPC 的脚本坏了不影响其它 NPC。

## 可读变量 ctx（只读视图，纯数据）

宿主每次开会话重建只读表，Lua 读到标量/嵌套表，不持有真实对象：

| 路径 | 类型 | 含义 / 值域 |
|---|---|---|
| `ctx.player.level` | number | 玩家等级 |
| `ctx.player.job` | number | 职业代码（`0`=新手、`3000`=弓箭手…） |
| `ctx.player.map` | number | 当前地图 id（出租车按图过滤用） |
| `ctx.npc.id` | string | 当前 NPC 的 id |
| `ctx.npc.name` | string | 当前 NPC 名字 |
| `ctx.jobdef.code/.name/.advance_lv` | number/string | 目标职业信息；**仅转职会话携带** |

## 可调用的宿主全局函数（副作用在宿主侧执行）

函数由宿主（`script_api.make_globals`）注册到沙箱，Lua 直接按名调用。
**参数传基本类型（string/number/boolean）**；返回的列表/表（如
`quest_completable`）会被折成 Lua 原生表，`#t`、`t[1].field`、`ipairs` 均可用。
注册按宿主上下文分级：**没注册的函数在脚本里不存在**，调用即报错（触发上表兜底）。

### 转职（仅转职会话注册：宿主 ctx 携带 `jobdef`）
| 函数 | 返回 | 副作用 |
|---|---|---|
| `can_advance()` | boolean | 无。判定玩家能否转职为 `ctx.jobdef` |
| `advance_job()` | nil | 改真身职业（附技能/武器），置宿主 `advanced` 标记；会话结束时宿主播升级音效并把对应 `adv_*` 任务置完成 |

### 发奖与切图（NPC 会话注册：宿主携带 `world`）
| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `give_reward(exp, meso, items)` | number/table | boolean | 直接发奖：经验、金币、物品；参数可省略。`items` 为 `[[item_id, count], ...]`，`count` 负数 = 收回 |
| `teleport(map_id)` | string/number | boolean | 登记切图请求；本次交互后会话关闭并由宿主执行切图 |

### 任务（NPC 会话注册：宿主携带 `world` + `quest_defs`）
| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `quest_available(npc_id)` | number/string | 数组[{qid,title,level,state}] | 该 NPC 可接取 + 可交付的任务（state=`offer`/`complete`） |
| `quest_completable(npc_id)` | number/string | 数组[{qid,title,level,state}] | 仅可交付的（state=`complete`） |
| `quest_state(qid)` | number/string | string | `"available"/"accepted"/"completed"` |
| `accept_quest(qid)` | number/string | boolean | 接取任务（条件不足 false） |
| `complete_quest(qid)` | number/string | boolean | 完成任务并**按 QuestDef 发奖**（exp/金币/物品、扣 end_items）；条件不足 false |
| `quest_info(qid)` | number/string | 表{name,reward_exp,reward_money} | 任务信息，未知 qid 返回空表 |

### 商店（NPC 会话注册：宿主携带 `world`）
| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `open_shop()` | 无 | boolean | 登记开店意图；本次交互后会话关闭并由宿主打开本 NPC 商店面板（`npc/1012119.lua` 演示） |
| `get_shop_items(shop_id)` | string | 数组[{item_id,price}] | 货架与买价（可用于 `talk()` 里报价文案） |
| `shop_buy(item_id, count)` / `shop_sell(item_id, count)` | string/int | boolean | 已注册但**暂不可用**，见「未提供」 |

### 未提供 / 后续扩展

- `shop_buy`/`shop_sell` 依赖宿主 `_current_shop` 定位货架，当前宿主从不置位，
  故在 `talk()` 里调用恒返回 `false`；对话内交易留待后续。
- 句内蓝字标记（`#L…#l` 内嵌渲染）：不做，蓝字一律整行（块级）。

## 对话路由：talk() 与默认会话的关系

`npc_dialogue.try_talk` 按优先级：

1. NPC 有 `content/npc/<id>.lua` 且导出 `talk()` → **完全接管对话**（默认菜单不出现）。
2. 否则该 NPC 有任务/进行中/传送条目 → 宿主**自动合成默认会话**（一张蓝字列表）：
   可交付在前、可接任务、进行中、传送目的地（剔除玩家当前图）、有商店则末尾加
   「商店」链接。点任务进入由 `entries()` Say 槽文本组成的子会话。
3. 有商店且以上皆空 → 直接开商店面板。
4. 其余 → 寒暄气泡（仓库 NPC 带 storage 按钮）。

因此：写 `talk()` 就要自己负责全部入口（任务、聊天等）；只想改数值/文案、
不加新流程时，可以不写 `talk()`，让宿主合成默认会话。

## 自定义 NPC 条目脚本（npc/<npc_id>.lua）

每个 NPC 可在 `npc/<npc_id>.lua` 里导出以下内容，启动期由
`lua_quests.load_lua_quest_defs()` 扫描 `resources/content/npc/` 加载：

| 函数 | 返回 | 说明 |
|---|---|---|
| `entries(ctx)` | 数组[条目] | 任务/传送条目；`type` 字段：`"quest"`（缺省）或 `"teleport"` |
| `shops()` | 数组[ShopDef] | NPC 的商店定义 |
| `talk(ctx)` | 会话定义 | 可选；见上文契约，接管该 NPC 的对话 |

`entries(ctx)` 的 `ctx` 恒为 `nil`（加载发生在启动期，玩家尚未构建）：任务条件
一律写在定义字段（`lvmin`/`kills`/`end_items` 等）由 `QuestLog` 判定，运行时
条件请写在 `talk()` 的 `show` 里。quest 条目按文件名+序号生成 qid
`c_<npc_id>_<序号>`（如 `c_1012119_1`），`talk()` 里的 `accept_quest` 等就引用它。

### 任务条目（`type = "quest"`，缺省）

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `"quest"` 或省略（缺省即 quest） |
| `name` | string | 任务名（必填，缺失则该条跳过） |
| `lvmin` / `lvmax` | number | 接取等级下限 / 上限（0 = 不限） |
| `jobs` | 数组[number] | 职业限制，空 = 不限 |
| `start_items` | 数组[[id,count]] | 接取时需持有该物品 |
| `prereq` | 数组[[qid,state]] | 前置任务（state 2=已完成 / 1=已接取） |
| `kills` | 数组[[mob,count]] | 完成需击杀怪物 |
| `end_items` | 数组[[item,count]] | 完成需收集物品 |
| `accept_items` | 数组[[item,count]] | 接取时赠送物品 |
| `reward_exp` / `reward_money` | number | 完成奖励经验 / 金币 |
| `reward_items` | 数组[[item,count]] | 完成奖励物品，负数=收回 |
| `next_quest` | number | 完成后解锁的后续任务（可选） |
| `accept_lines` | 数组[string] | 接取询问文本 |
| `accept_yes` / `accept_no` | 数组[string] | 接取确认 / 拒绝文本 |
| `complete_lines` | 数组[string] | 完成询问文本 |
| `complete_yes` | 数组[string] | 领取奖励文本 |
| `complete_stop` | 数组[string] | 条件未满足时的提示 |
| `desc0` / `desc1` / `desc2` | string | 任务日志描述（可选） |

> `accept_lines` 等六个 Say 槽位是「NPC **未写 `talk()`** 时默认子会话」的对话文本；
> 写了 `talk()` 则完全不用它们（但任务数值字段仍然生效：接取/交付判定、奖励发放、
> 头顶灯泡、存档）。缺省槽位有宿主兜底文案。

任务对话文本槽位支持官方标记（宿主 `render_markup`）：`#t<id>#` 物品名、
`#o<id>#` 怪物名、`#m<id>#` 地图名、`#p<id>#` NPC 名、`#b/#r/#k` 颜色、`\n` 换行。

### 传送条目（`type = "teleport"`）

```lua
function M.entries(ctx)
  return {
    { type = "teleport", label = "射手村",   map = "100000000" },
    { type = "teleport", label = "魔法密林", map = "101000000" },
  }
end
```

- Lua 是传送目的地的**唯一事实来源**：Python 不再持有出租车名单或目的地表。
- `label` 为菜单显示名，`map` 为目标地图 id（字符串）。
- 不写 `talk()` 时目的地进默认会话蓝字列表（自动剔除玩家当前图）；
  写了 `talk()` 则在链接里自己调 `teleport(map)`。
- 玩家点选后经 `Game._enter_map` 切图，落在目标图的 `sp` 出生门。
- 未知 `type` 的条目会被跳过并记录 warning。

### 商店定义（`shops()`）

```lua
{
  shop_id = "potions",          -- 可省略，自动生成 <npc_id>_shop_<序号>
  name = "药水",                 -- 页签显示名，缺省回退 shop_id
  items = {
    {item_id = "02000000", price = 50},
    {item_id = "02000003", price = 100},
  }
}
```

- Lua 是商店的**唯一事实来源**：货架、买价、名称全部由 `shops()` 定义，
  Python 不再有硬编码商店；未定义 `shops()` 的 NPC 无商店。
- `items` 中的 `price` 为买价（脚本价优先于 WZ `info.price` 与兜底表）；
  卖价按 `SELL_RATE` 自动计算。

### 沙箱与失败隔离

- 与 `talk()` 同一套沙箱：禁用 `os`/`io`/`package`/`debug`/`dofile`/`loadfile`。
- 单个脚本加载失败或单条任务翻译失败，只跳过该条并记录 warning，
  不影响其它 NPC/任务。

## 编写规范

- 语言：文件内注释用简体中文；一个步骤一个 `text` 数组；语义要拆分就多写几行。
- 插值/格式化用 Lua 拼接 `..` 或 `string.format("（当前 Lv%d…）", ctx.player.level)`。
- 官方/自定义**任务数值**写在 `entries()` 定义字段里，由 `QuestLog` 判定与发奖；
  **自定义发奖**（不属于任何任务的赠与）则相反——直接 `give_reward` 把数值写在
  `talk()` 里。
- `show` 条件只读 `ctx` 与宿主查询函数；副作用（accept/complete/发奖/切图）只在
  `click`/按钮函数里做。
- 改完可用 `uv run python -m game.main` 进游戏试；或跑单测：
  `uv run pytest src/tests/test_lua_talk_demo.py src/tests/test_lua_advance.py`
  （1012119 演示与转职脚本路径）。
