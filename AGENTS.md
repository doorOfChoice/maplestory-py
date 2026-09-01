# AGENTS.md

本文件为开发者与 AI agent 共用的开发规范与代码导览。改动代码前请先读一遍，特别注意「样式约定」与「测试规范」。

## 项目概览

MapleStory v113 的 pygame 单机重制。游戏直接读取 `wz/` 下的官方 WZ 资产（只读），由自制的 `wzpy` 函数库解析、解密并渲染成 pygame 画面。

- **Python ≥ 3.12**，包管理用 `uv`
- **src 布局**：所有代码（`game`、`wzpy`、`tests`、`scripts`）都位于 `src/` 下，透过可编辑安装（editable）暴露为顶层包；`src/scripts/` 放独立脚本（如 `capture_screenshots.py`），按路径运行、不打包进发行版
- **两层架构**：
  - `src/wzpy/` —— 函数库层：WZ 封存格式解析（解密、属性树、图片解码）、Map/Mob/Character 渲染器、JSON 导出。可独立重复使用。
  - `src/game/` —— 应用层：游戏循环、物理、实体（玩家/怪物/NPC）、战斗、技能、背包、任务、UI。
- `wz/` 目录本身入库（仅 `.gitkeep` 占位），目录内的 WZ 文件已 gitignore，不提交。

## 常用命令

```bash
uv sync            # 安装依赖（含 dev 组），并安装本项目为可编辑包
uv run python -m game.main   # 启动游戏
uv run python src/scripts/capture_screenshots.py   # 重新生成 README 截图
uv run pytest      # 跑测试（testpaths = src/tests）
```

pyproject.toml 已设定 pytest 的 `pythonpath = ["src"]` 与 `testpaths = ["src/tests"]`。

## 架构要点

### 数据流

```
WZ (.wz) → wzpy: WzFile.open → 解密 → 目录树 → 惰性属性解析
        → Renderer (Map/Mob/Character) → PIL Image
        → src/game/assets.py: pil_to_surface 缓存 → pygame Surface
        → 场景绘制（canvas → camera → display，固定 60 FPS）
```

### 游戏循环（src/game/game.py）

每帧：`clock.tick(FPS)`（dt 上限 35ms 防物理隧穿）→ `_handle_input` → `_update(dt)`（玩家/怪物/战斗/相机）→ `_draw`（场景、UI、面板、对话、死亡画面）。

### 关键设计决定

- **坐标系统**：沿用 WZ 世界坐标（y 向下为正），角色以 navel 为锚点，脚底 = navel + `FEET_OFFSET`（20px）
- **物理**（src/game/physics.py）：自制的 MS 式 foothold 行走系统，非回合制碰撞 —— 落地只发生在「脚底本帧跨越 foothold 线」时；爬墙只沿当前 foothold 的 prev/next 链；含梯子/绳、蹬墙跳
- **WZ 资产只读**：本项目只读 `wz/`，永不写入
- **惰性解析**：WZ 影像首次访问才解析，并积极缓存
- **非模态对话**：NPC/任务对话不暂停世界
- **常量集中**：所有物理/战斗/背包常量集中在 `src/game/settings.py`（含文件头说明）

## 样式约定

- **语言**：模块 docstring、类别说明、行内注释一律使用**简体中文**；文件采布局注释分隔（`# ── 区块 ──`、`# ═══`）
- **`from __future__ import annotations`**：每个文件顶部必加
- **导入顺序**：标准库 → 第三方 → 本项目，以空行分隔；`src/game/` 内用相对导入（`from . import settings`），跨包用绝对导入（`from wzpy.wz_file import WzFile`）；禁用 `import *`
- **命名**：
  - 类别 `PascalCase`、函数/方法 `snake_case`、模块常量 `UPPER_SNAKE_CASE`、私有成员前缀单下划线 `_`、文件名 `snake_case.py`
- **类型标注**：所有函数签名都应有类型标注与返回类型；用 Python 3.10+ union 语法（`Optional[x]` 等）；可变默认值用 `dataclasses.field(default_factory=...)`；物理热点类别用 `__slots__`
- **docstring**：模块层描述用途、坐标约定、设计哲学（见 `src/game/settings.py`、`src/game/physics.py` 示例）
- **行长**：约 100~120 字符为上限，勿硬折
- **缩进**：4 空格
- **不写无意义注释**，也不为代码注释过度铺陈；除非必要，不加注释

## 测试规范

- 框架 **pytest**，整颗整合式测试：透过**公开接口**验证行为，不用 mock、不用 fixture、不探索私有成员（见 `.agents/skills/tdd/`）
- 文件名 `test_<feature>.py`、函数 `test_<行为描述>()`（纯函数，不用类别）
- 测试数据用模块层辅助函数建构（如 `fh()`、`make()`）；一个测试一个逻辑断言；测试彼此独立、无共享状态
- 纯单元测试不需 WZ 文件（用合成 foothold 资料构造 `Physics`）
- 惯例注释：测试 docstring 描述**被验证的行为**（与代码注释同样用简体中文）
- 新功能或修 bug 时遵循 TDD：红灯先写、一次一片（vertical slice）、测公开 seam，先与使用者确认要测的 seam

## 数据与资产 (wz/)

`wz/` 下为 MapleStory v113（台湾版）官方 WZ 封存（Map / Mob / Character / Npc / String / Sound ...），仅供本项目执行时读取，**WZ 文件不得提交 Git**（目录本身以 `.gitkeep` 入库）。资产获取方式见 README「获取 WZ 资产」。改动需新增 WZ 依赖的测试时，不可假设 CI 环境有 WZ 文件，请以合成资料取代。
