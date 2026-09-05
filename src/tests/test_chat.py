"""聊天框模型：聚焦态、输入缓冲编辑、发送语义、日志滚动上限、无操作自动消失。"""

from typing import Callable, Tuple

from game.core.chat import LOG_TTL_SECONDS, MAX_LOG_LINES, Chat


def make_chat() -> Tuple[Chat, Callable[[float], None]]:
    """带可控假时钟的 Chat：advance(秒) 拨动当前时间。"""
    t = [0.0]

    def advance(seconds: float) -> None:
        t[0] += seconds

    return Chat(now=lambda: t[0]), advance


def test_enter_chat_opens_and_closes_without_losing_log():
    """聚焦→关闭只清缓冲，日志保留（下次打开还能看到历史）。"""
    chat = Chat()
    chat.open()
    assert chat.focused
    chat.type("你好")
    chat.close()
    assert not chat.focused
    assert chat.text == ""
    assert [ln.text for ln in chat.lines] == []


def test_typed_segments_append_in_order():
    """TEXTINPUT 分段进缓冲（逐字符 / IME 整段都走同一接口）。"""
    chat = Chat()
    chat.open()
    chat.type("he")
    chat.type("llo ")
    chat.type("世界")
    assert chat.text == "hello 世界"


def test_backspace_deletes_one_character():
    """退格一次删一个字符（含中文，按字符而非字节）。"""
    chat = Chat()
    chat.type("你好a")
    chat.backspace()
    assert chat.text == "你好"
    chat.backspace()
    chat.backspace()
    chat.backspace()          # 空缓冲再退格不应报错
    assert chat.text == ""


def test_submit_returns_text_and_clears_buffer():
    """发送返回本轮文本并清空缓冲（聚焦态由调用方决定去留）。"""
    chat = Chat()
    chat.type("/heal")
    assert chat.submit() == "/heal"
    assert chat.text == ""


def test_submit_on_empty_buffer_returns_none():
    """空内容发送 → None（调用方据此关闭聊天框）。"""
    assert Chat().submit() is None


def test_log_keeps_most_recent_lines():
    """日志超过上限时丢弃最旧行，保留最近 MAX_LOG_LINES 条。"""
    chat = Chat()
    total = MAX_LOG_LINES + 5
    for i in range(total):
        chat.add("system", f"第{i}条")
    assert len(chat.lines) == MAX_LOG_LINES
    assert chat.lines[0].text == f"第{total - MAX_LOG_LINES}条"
    assert chat.lines[-1].text == f"第{total - 1}条"


def test_log_lines_carry_kind():
    """每条日志带类型（player/system/error），供渲染层着色。"""
    chat = Chat()
    chat.add("player", "大家好")
    chat.add("error", "未知指令")
    assert [ln.kind for ln in chat.lines] == ["player", "error"]


def test_log_expires_after_idle_timeout():
    """日志静默超过 LOG_TTL_SECONDS 后 expire 清空（面板自动消失）。"""
    chat, advance = make_chat()
    chat.add("system", "/heal 已恢复")
    advance(LOG_TTL_SECONDS - 0.1)
    chat.expire()
    assert chat.lines
    advance(0.2)
    chat.expire()
    assert chat.lines == []


def test_activity_delays_expiry():
    """任何操作（打字 / 新日志）刷新活跃时间，5 秒从最后一次操作起算。"""
    chat, advance = make_chat()
    chat.add("system", "第一条")
    advance(LOG_TTL_SECONDS - 1.0)
    chat.open()
    chat.type("/warp")
    advance(LOG_TTL_SECONDS - 1.0)      # 距最后操作 4s，未超时
    chat.close()
    chat.expire()
    assert chat.lines
    chat.add("system", "第二条")         # 新日志同样续命
    advance(LOG_TTL_SECONDS + 0.1)
    chat.expire()
    assert chat.lines == []


def test_expiry_paused_while_focused():
    """聚焦输入中不清日志（无操作指面板闲置，不含正在打字）。"""
    chat, advance = make_chat()
    chat.add("system", "历史")
    chat.open()
    advance(LOG_TTL_SECONDS + 1.0)
    chat.expire()
    assert chat.lines
