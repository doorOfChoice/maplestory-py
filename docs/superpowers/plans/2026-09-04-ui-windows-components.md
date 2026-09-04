# 面板组件化重构实施计划（UI Windows Components）

**目标**：把背包/装备/技能/任务日志/状态/按键设置/商店/仓库 8 个面板从面向函数的上帝类（`Panels` 1495 行 + 平行实现的 `ShopPanel`/`StoragePanel`）重构为 `Window` 组件 + `WindowManager` 统一分发，消除 chrome/滚动/tooltip/toast/拖拽重复代码。

**架构**：新建 `src/game/render/windows/` 子包。保留「绘制帧重建热区、事件帧命中回放」的即时模式；跨窗口关注点（物品拖扔、toast、tooltip、z 序、窗口→VIEW 坐标缩放、Esc 关闭）上收 `WindowManager`。对话层（`ui.show_dialog` / conversation 面板）**不动**。

**技术栈**：pygame + `Assets.ui_surface`（UIWindow.img / StatusBar.img），无新依赖。

**迁移策略**：一步到位。基座（Task 1）冻结共享接口后，Task 2–6 五个窗口组**并行**由子代理实现（文件所有权互不重叠）；Task 7 统一接线 `game.py`/`context.py` 并删除旧类，测试同步改打新 seam。旧 `panels.py`/`shop_panel.py`/`storage_panel.py` 在 Task 7 前保留（只读参考，不再被引用处逐步切换）。

**Spec**：本文件即实施 spec；迁移源码行号参考各窗口任务括号内标注。

## Global Constraints

- Python ≥ 3.12；每文件 `from __future__ import annotations`；绝对导入；简体中文注释/docstring；全签名类型标注；行宽 ≤120；4 空格。
- 测试：pytest，纯函数、无 fixture、无 mock 框架；测试数据用模块层助手函数；FakeUI/FakeAssets 放 `src/tests/windows_harness.py`；不依赖 WZ 文件（`ui_surface` 一律返回 None → 全走 fallback 自绘路径，行为等价）。
- 验证命令：`uv run pytest`（testpaths=src/tests）；每个任务收尾全绿。
- UI 层不触碰世界：扔地落地仍由 `game.py` 调 `combat.drop_player_item` + 音效（manager 只暂存 `take_dropped()`）。
- 行为不变的细节不得顺手改：双击阈值 0.35s、拖拽阈值 6px、toast 文案、fallback 布局、素材缺失回退。唯一允许的新行为：重叠窗口点击置顶（z 序）。

## 文件结构

```
src/game/render/windows/
  __init__.py      # 导出 Window / WindowManager / WindowServices / DragPickup
  services.py      # WindowServices
  window.py        # Window 基类（chrome/定位/事件契约）
  widgets.py       # wz_surface/ui_button_surface/ellipsize/draw_menu_bg/tooltip/toast/PixelNumbers/ScrollList/fit_icon
  manager.py       # WindowManager
  stat.py          # StatWindow            （panels.py:1101-1250 迁移）      [代理A]
  questlog.py      # QuestLogWindow        （panels.py:1026-1099 迁移）      [代理A]
  skill.py         # SkillWindow           （panels.py:826-1024 迁移）       [代理B]
  inventory.py     # InventoryWindow + EquipWindow（panels.py:127 起背包/装备 + 拖扔）[代理C]
  keyconfig.py     # KeyConfigWindow       （panels.py:218-226,395-415,1253-1322）[代理D]
  shop.py          # ShopWindow            （shop_panel.py 688 行迁移）      [代理E]
  storage.py       # StorageWindow         （storage_panel.py 迁移）         [代理E]
  quickslot.py     # QuickSlotBar（常驻、无 chrome、不消费点击）（panels.py:1324-1397）[Task7 由主控实现]
```

## 接口契约（Task 1 冻结，代理按此编码）

```python
# services.py
@dataclass
class WindowServices:
    assets: Assets                      # ui_surface / item_icon / equip_icon / skill_icon / mob_name_of ...
    ui: UI                              # 只用 font/font_small/font_tiny 与 _wrap
    player: Callable[[], Player]        # 惰性取当前玩家
    bindings: Optional[KeyBindings] = None
    combat: Optional[Combat] = None     # 卷轴扣费 / 商店金币
    quest_goal_lines: Optional[Callable[[str], List[str]]] = None
    flash: Callable[[str], None] = _noop          # 接线后 = manager.flash
    tooltip: Callable[[str], None] = _noop        # 接线后 = manager.set_tooltip（仅 draw 期调用）

# window.py
@dataclass
class DragPickup:
    source: tuple            # ("cell", tab, idx) | ("slot", slot) | 窗口自定义
    item: "Item"
    home: pygame.Rect        # 来源窗口外框：拖出即扔的判定框

class Window:
    key: str = ""
    escape_closes: bool = False        # Esc 优先关闭（keyconfig/shop/storage）
    def __init__(self, svc: WindowServices): ...
    visible: bool
    rect: pygame.Rect                  # 当前帧外框（place() 更新）
    title_rect: Optional[pygame.Rect]  # None = 本帧未画 chrome
    close_rect: Optional[pygame.Rect]
    def open/close/toggle(self) -> None; def on_close(self) -> None   # 子类清私有态
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:            # 默认左上角
    def place(self, surface, size: Tuple[int, int]) -> Tuple[int, int]  # 定位+限幅，画前调用
    def move_by_drag(self, x: int, y: int, vw: int, vh: int) -> None   # manager 拖标题时调用
    def add_chrome(self, surface, x, y, w, title_h) -> None            # 标题热区+关闭钮
    # 事件（pos = VIEW 坐标；返回 True = 已消费）
    def handle_mouse_down(self, pos) -> bool: ...
    def handle_wheel(self, pos, amount: int) -> bool: ...
    def handle_right_click(self, pos) -> bool: ...
    def handle_keydown(self, key: int) -> bool: ...
    def pickup(self, pos) -> Optional[DragPickup]: ...
    def activate(self, pk: DragPickup) -> None: ...
    def take_for_drop(self, pk: DragPickup) -> Optional[Item]: ...
    def draw(self, surface) -> None: ...

# manager.py
class WindowManager:
    def __init__(self, svc: WindowServices): ...
    def add(self, win: Window) -> Window            # 返回自身便于链式；注册序 = 默认 z 序（后加在上）
    def get(self, key: str) -> Window
    @property
    def windows(self) -> List[Window]               # 底 → 顶
    def flash(self, text, duration=1.6) / def set_tooltip(self, text)
    def dispatch(self, event: pygame.event.Event) -> bool   # 内部完成 WINDOW→VIEW 缩放（同 game.py 现算法）；
        # LMB：全局扫 close_rect → 顶到底扫 title_rect（起窗口拖拽）→ pickup（起物品拖拽/双击）
        #      → 首个 rect 包含点且 handle_mouse_down=True 者消费并置顶
        # WHEEL/MOUSEMOTION/UP/RMB 分发顶到底首个 rect 命中窗口；未消费返回 False 穿透给世界
    def dispatch_key(self, key: int) -> bool        # 顶到底 handle_keydown（keyconfig 录入态）
    def handle_escape(self) -> bool                 # 顶到底关首个 escape_closes 且 visible 者
    def take_dropped(self) -> Optional[Item]        # game.py 每帧取走拖出扔地的物品
    def close_npc_windows(self) -> None             # 切图：关商店/仓库（closes_on_map_change=True）
    def any_dragging(self) -> bool
    def draw(self, surface) -> None                 # z 序绘制 + 全局 tooltip/跟手拖拽图标/toast
```

事件常量：manager 只识别 `pygame.MOUSEBUTTONDOWN(1/3/4/5)`、`MOUSEMOTION`、`MOUSEBUTTONUP(1)`；其余返回 False。

## 任务分解

### Task 1（主控·串行）：基座
**Create**: `windows/{__init__,services,window,widgets,manager}.py`、`src/tests/windows_harness.py`、`src/tests/test_windows_core.py`
- 红灯→实现：标题拖拽移动并限幅；关闭钮消费点击且只关该窗；重叠窗口置顶者独享点击；滚轮只给命中窗口；WINDOW→VIEW 坐标缩放；未命中返回 False 穿透；`take_dropped` 一次取走；双击（<0.35s 同 source）触发 `activate`、超阈值拖出 `home` 触发 `take_for_drop`；Esc 按 `escape_closes` 关闭；`dispatch_key` 录入态消费。
- widgets：`ui_button_surface(svc, prefix, rect, mouse, pressed=False)`（WZ normal/mouseOver/pressed 三态）、`ellipsize`、`draw_menu_bg`、`draw_tooltip`、`draw_toast`、`PixelNumbers`（StatusBar/number 染色缓存）、`ScrollList(step).scroll(amount,total,visible)` 限幅、`fit_icon`。
- harness：`FakeUI`（真 pygame.font，dummy driver + `pygame.init()`）、`FakeAssets`（全 None/空串）、`make_services(player)`、`make_manager(*wins)`、事件助手 `press/release/motion/wheel/right_click/key/dispatch_all`。

### Task 2（代理A）：StatWindow + QuestLogWindow
**Create**: `windows/stat.py`、`windows/questlog.py`、`tests/test_windows_stat.py`、`tests/test_windows_questlog.py`
- 测：AP=0 点「+」→ `svc.flash("没有可分配的属性点")`；有 AP 加点生效；一键分配；页签无关；任务日志走 `svc.quest_goal_lines`，空态文案「目前没有进行中的任务」。像素数字用 `widgets.PixelNumbers`。

### Task 3（代理B）：SkillWindow
**Create**: `windows/skill.py`；**Delete+改写**: `tests/test_panels_scroll.py` → `tests/test_windows_skill_scroll.py`
- 测：转数页签切换重置滚动；滚轮限幅；点升级按钮 `player.skills.learn`。`widgets.ScrollList`。

### Task 4（代理C）：InventoryWindow + EquipWindow + 拖扔接线
**Create**: `windows/inventory.py`、`tests/test_windows_drag_drop.py`；**Delete**: `tests/test_panels_drag_drop.py`
- 测（经 manager.dispatch 全链路）：拖出扔地→`mgr.take_dropped()`；拖回取消；双击喝药回 HP、双击装备穿上、纸娃娃格拖出=脱下回传且 `refresh_equips`；穿戴门控 `wear_block` → flash 文案；卷轴 `_apply_scroll` 流程（combat.meso 扣费）；I 键 toggle 同开 inv+equip（`mgr.toggle("inventory")` 组：inventory.py 提供 `toggle_inventory_pair(mgr)` 助手，game.py Task7 调用）。
- `_item_tip`/`SLOT_NAMES`/`TAB_INDEX`/`INV_*`/`EQP_*` 常量随迁。

### Task 5（代理D）：KeyConfigWindow
**Create**: `windows/keyconfig.py`、`tests/test_windows_keyconfig.py`；**Delete**: `tests/test_panels_keyconfig.py`
- 测：行点击进录入态 → `dispatch_key` 改绑并 `bindings.save()`、Esc 取消；右键行 reset；滚轮；`skill_N` 行显示槽上技能名。

### Task 6（代理E）：ShopWindow + StorageWindow
**Create**: `windows/shop.py`、`windows/storage.py`、`tests/test_windows_shop.py`；**Delete**: `tests/test_shop_panel.py`；`tests/test_storage.py` 仅改面板引用
- 测：货架/背包双滚动条（thumb 拖拽）、页签切换、买卖按钮、仓库存取回背包；`open(npc_id)/close`；`closes_on_map_change=True`、`escape_closes=True`。toast 用 manager 全局。

### Task 7（主控·串行）：接线与退役
- `context.py`：装配 `WindowServices` + `WindowManager` + 全窗口 + `QuickSlotBar`（`windows/quickslot.py`，本任务实现）；`ctx.windows` 取代 `panels/shop_panel/storage_panel`。
- `game.py`：输入块 → `self.ctx.windows.dispatch(event)`（对话仍最先消费）；`consume_binding_key` → `dispatch_key`；Esc 链 → `handle_escape`；`take_dropped` → `combat.drop_player_item` + 音效；`_enter_map` → `close_npc_windows`；`_draw` → `windows.draw(canvas)`。
- 删除 `panels.py`/`shop_panel.py`/`storage_panel.py`；`npc_dialogue.py`/`script_api.py` 中 `shop_panel` 引用切 `ctx.windows.get("shop").open(npc_id)`（同语义）。
- 全量 pytest 绿 + `uv run python -m game.main` 冒烟（8 面板开合/拖拽/扔物/商店/改绑/置顶）。

## 并行与验收规则（代理必读）

1. 只许创建/修改「Create/Delete」列出的文件；**禁止**编辑 `window.py/widgets.py/manager.py/services.py/windows_harness.py/windows/__init__.py` 与其他代理的文件。
2. 共享层缺口：先在自己窗口文件内写模块级私有函数兜底；确需改共享层的，在最终汇报中列出「GAP:」说明，由主控整合时处理。
3. 每个代理收尾运行 `uv run pytest src/tests/<自己的测试文件>`（可跑全量但不得为绿灯去改别人的测试）。
4. 不做 git 操作、不新增依赖、不动 `game.py`/`context.py`。
5. 汇报格式：改动文件清单、测试结果摘要、GAP 列表、与旧行为差异说明（应为零，除注明）。
