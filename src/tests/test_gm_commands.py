"""GM 指令解析与分发：/ 前缀识别、参数校验、回调接线、未知命令提示。"""

from game.systems.gm import GmContext, execute, is_command


class Recorder:
    """记录被调用的回调参数，返回预置结果（FakeAssets 同款手搓替身）。"""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def make_ctx(warp_result=("system", "正在传送")):
    return GmContext(warp=Recorder(warp_result), heal=Recorder(("system", "已恢复")),
                     meso=Recorder(("system", "金币已增加")))


# ── 前缀识别 ────────────────────────────────────────────────────────

def test_slash_prefix_marks_command():
    assert is_command("/warp 100")
    assert not is_command("大家好")
    assert not is_command("//不是指令 ")   # 双斜杠当普通发言


# ── /warp ───────────────────────────────────────────────────────────

def test_warp_passes_map_id_to_context():
    ctx = make_ctx()
    lines = execute("/warp 100000000", ctx)
    assert ctx.warp.calls == [("100000000",)]
    assert lines == [("system", "正在传送")]


def test_warp_maps_not_found_error_from_context():
    """地图不存在时错误来自 ctx.warp 的返回值，原样上屏。"""
    ctx = make_ctx(warp_result=("error", "地图 999999999 不存在"))
    lines = execute("/warp 999999999", ctx)
    assert lines == [("error", "地图 999999999 不存在")]


def test_warp_without_arg_shows_usage_and_does_not_warp():
    ctx = make_ctx()
    lines = execute("/warp", ctx)
    assert ctx.warp.calls == []
    assert lines and lines[0][0] == "error"
    assert "/warp <地图id>" in lines[0][1]


def test_warp_rejects_non_numeric_id():
    ctx = make_ctx()
    lines = execute("/warp 弓箭手村", ctx)
    assert ctx.warp.calls == []
    assert lines[0][0] == "error"


def test_warp_rejects_extra_args():
    ctx = make_ctx()
    lines = execute("/warp 100 200", ctx)
    assert ctx.warp.calls == []
    assert lines[0][0] == "error"


# ── /heal 与 /meso ──────────────────────────────────────────────────

def test_heal_invokes_context():
    ctx = make_ctx()
    lines = execute("/heal", ctx)
    assert ctx.heal.calls == [()]
    assert lines == [("system", "已恢复")]


def test_meso_parses_amount():
    ctx = make_ctx()
    execute("/meso 5000", ctx)
    assert ctx.meso.calls == [(5000,)]


def test_meso_rejects_bad_amount():
    ctx = make_ctx()
    lines = execute("/meso abc", ctx)
    assert ctx.meso.calls == []
    assert lines[0][0] == "error"


def test_meso_rejects_negative():
    ctx = make_ctx()
    lines = execute("/meso -100", ctx)
    assert ctx.meso.calls == []
    assert lines[0][0] == "error"


# ── 通用 ────────────────────────────────────────────────────────────

def test_unknown_command_reports_name():
    ctx = make_ctx()
    lines = execute("/fly me", ctx)
    assert lines[0][0] == "error"
    assert "fly" in lines[0][1]


def test_command_name_is_case_insensitive():
    ctx = make_ctx()
    execute("/WARP 100", ctx)
    assert ctx.warp.calls == [("100",)]


def test_help_lists_all_commands():
    """多空格分隔容错；/help 输出覆盖全部已注册指令名。"""
    lines = execute("/help", make_ctx())
    text = "\n".join(t for _, t in lines)
    for name in ("warp", "heal", "meso", "help"):
        assert name in text
