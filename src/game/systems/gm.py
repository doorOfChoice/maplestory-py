"""GM 指令：`/命令 参数…` 的解析与分发（纯逻辑，不依赖 Game/pygame）。

设计：命令注册表 name → CommandDef(usage, 说明, handler)，handler 只经
GmContext 的回调与世界互动（由 game.py 注入），返回 [(kind, 文本)] 聊天行。
本模块不认识 Game 对象，测试用录制替身即可覆盖全部路径。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

# 聊天行：(kind, text)，kind ∈ player/system/error
Lines = List[Tuple[str, str]]


@dataclass(frozen=True)
class GmContext:
    """世界侧能力注入：每个回调返回一条 (kind, 文本) 反馈。"""

    warp: Callable[[str], Tuple[str, str]]      # 地图 id → 反馈
    heal: Callable[[], Tuple[str, str]]
    meso: Callable[[int], Tuple[str, str]]      # 数量（正整数）→ 反馈
    add_level: Callable[[int], Tuple[str, str]] = \
        lambda _n: ("system", "等级已提升")      # 加 N 级（正整数）→ 反馈
    drop_rate: Callable[[int], Tuple[str, str]] = \
        lambda _n: ("system", "装备掉落率已调整")      # 装备掉落倍率（正整数）→ 反馈


@dataclass(frozen=True)
class CommandDef:
    name: str
    usage: str          # 参数部分（空串 = 无参）
    desc: str
    handler: Callable[[Sequence[str], GmContext], Lines]


def _bad_usage(cmd: CommandDef) -> Lines:
    full = f"/{cmd.name}" + (f" {cmd.usage}" if cmd.usage else "")
    return [("error", f"用法：{full}")]


def _cmd_warp(args: Sequence[str], ctx: GmContext) -> Lines:
    if len(args) != 1 or not args[0].isdigit():
        return _bad_usage(COMMANDS["warp"])
    return [ctx.warp(args[0])]


def _cmd_heal(args: Sequence[str], ctx: GmContext) -> Lines:
    return [ctx.heal()] if not args else _bad_usage(COMMANDS["heal"])


def _cmd_meso(args: Sequence[str], ctx: GmContext) -> Lines:
    if len(args) != 1 or not args[0].isdigit() or int(args[0]) <= 0:
        return _bad_usage(COMMANDS["meso"])
    return [ctx.meso(int(args[0]))]


def _cmd_add_level(args: Sequence[str], ctx: GmContext) -> Lines:
    if len(args) != 1 or not args[0].isdigit() or int(args[0]) <= 0:
        return _bad_usage(COMMANDS["addlevel"])
    return [ctx.add_level(int(args[0]))]


def _cmd_drop_rate(args: Sequence[str], ctx: GmContext) -> Lines:
    if len(args) != 1 or not args[0].isdigit() or int(args[0]) <= 0:
        return _bad_usage(COMMANDS["droprate"])
    return [ctx.drop_rate(int(args[0]))]


def _cmd_help(args: Sequence[str], ctx: GmContext) -> Lines:
    return [("system", f"/{c.name}" + (f" {c.usage}" if c.usage else "")
             + f" —— {c.desc}") for c in COMMANDS.values()]


COMMANDS: Dict[str, CommandDef] = {
    c.name: c for c in (
        CommandDef("warp", "<地图id>", "传送到目标地图出生点", _cmd_warp),
        CommandDef("heal", "", "恢复满血满蓝", _cmd_heal),
        CommandDef("meso", "<数量>", "增加金币", _cmd_meso),
        CommandDef("addlevel", "<等级数>", "在当前等级基础上加 N 级", _cmd_add_level),
        CommandDef("droprate", "<倍率>", "临时提高装备掉落率（1 恢复）", _cmd_drop_rate),
        CommandDef("help", "", "列出全部指令", _cmd_help),
    )
}


def is_command(text: str) -> bool:
    """单个 `/` 开头即 GM 指令；`//` 视为普通发言。"""
    return text.startswith("/") and not text.startswith("//")


def execute(text: str, ctx: GmContext) -> Lines:
    """解析并执行一条 `/命令`；参数解析在此完成，世界效果走 ctx 回调。"""
    parts = text.lstrip("/").split()
    name = parts[0].lower() if parts else ""
    cmd = COMMANDS.get(name)
    if cmd is None:
        return [("error", f"未知指令：/{name}（输入 /help 查看全部）")]
    return cmd.handler(parts[1:], ctx)
