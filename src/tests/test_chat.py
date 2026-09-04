"""聊天框模型：聚焦态、输入缓冲编辑、发送语义、日志滚动上限。"""

from game.core.chat import MAX_LOG_LINES, Chat


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
