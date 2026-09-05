"""出租车传送：Lua entries() 按类型翻译 + travel 注册表 + 对话菜单扣费。"""

from __future__ import annotations

import pygame

from game.core import travel
from game.npc_dialogue import NpcDialogueController
from game.systems.lua_quests import load_lua_quest_defs

_MIXED_LUA = """
local M = {}
function M.entries(ctx)
  return {
    { type = "quest", name = "打地兽", lvmin = 5, kills = { { 100101, 3 } } },
    { type = "teleport", label = "射手村", map = "100000000", fare = 1000 },
    { type = "teleport", label = "废弃都市", map = "103000000" },
    { type = "warp_whatever", label = "未知类型" },
  }
end
return M
"""


def _write(dir, name: str, src: str) -> None:
    (dir / name).write_text(src, encoding="utf-8")


def test_entries_split_by_type(tmp_path):
    """entries() 里 quest 条目进任务表、teleport 条目进传送注册表、未知类型跳过。"""
    travel.clear_teleports()
    _write(tmp_path, "9900001.lua", _MIXED_LUA)
    defs = load_lua_quest_defs(tmp_path)
    assert len(defs) == 1
    d = next(iter(defs.values()))
    assert d.name == "打地兽"
    assert d.start_npc == 9900001
    assert travel.teleports_of("9900001") == [
        ("射手村", "100000000", 1000), ("废弃都市", "103000000", 0)]


def test_teleports_exclude_current_map(tmp_path):
    """已在目的地图时，该目的地从菜单剔除。"""
    travel.clear_teleports()
    _write(tmp_path, "9900002.lua", _MIXED_LUA)
    load_lua_quest_defs(tmp_path)
    names = [n for n, _, _ in travel.teleports_of("9900002", "100000000")]
    assert names == ["废弃都市"]


def test_legacy_quests_fn_not_loaded(tmp_path):
    """旧契约 quests() 不再被识别。"""
    travel.clear_teleports()
    _write(tmp_path, "9900003.lua",
           "local M = {}\nfunction M.quests(ctx) return { { name='x' } } end\nreturn M\n")
    assert load_lua_quest_defs(tmp_path) == {}


# ── 对话菜单扣费 ────────────────────────────────────────────────────

class FakeNPC:
    def __init__(self, npc_id: str, name: str) -> None:
        self.npc_id = npc_id
        self.name = name
        self._rect = pygame.Rect(100, 100, 40, 60)

    def rect(self) -> pygame.Rect:
        return self._rect


class FakePlayer:
    def __init__(self) -> None:
        self.x = 120.0
        self.y = 130.0
        self.quests = None


class FakeCombat:
    def __init__(self, meso: int) -> None:
        self.meso = meso


class FakeWorld:
    def __init__(self, npcs, meso: int) -> None:
        self.npcs = npcs
        self.player = FakePlayer()
        self.combat = FakeCombat(meso)


class FakeAssets:
    map_id = "100000000"
    map_name_of = staticmethod(lambda mid: str(mid))
    npc_name = staticmethod(lambda nid: "NPC")
    item_name = staticmethod(lambda iid: "物品")
    mob_name_of = staticmethod(lambda mid: "怪物")


class FakeConvPanel:
    """替身会话面板：记录 show 快照，link_hit 按登记的索引回点。"""

    def __init__(self) -> None:
        self.shown = []
        self._hit_index = None

    def show(self, title, lines, links, buttons, terminal, npc_id=None):
        self.shown.append(links)

    def hide(self):
        pass

    def set_hit(self, index):
        self._hit_index = index

    def link_hit(self, pos):
        return self._hit_index

    def button_hit(self, pos):
        return None

    def panel_hit(self, pos):
        return True

    @property
    def visible(self):
        return True


class FakeUI:
    def __init__(self) -> None:
        self.conv = FakeConvPanel()
        self.dialog_visible = False

    def show_dialog(self, *a, **k):
        pass

    def hide_dialog(self):
        pass

    def dialog_button_hit(self, pos):
        return None

    def dialog_hit(self, pos):
        return False


class FakeWindows:
    def __init__(self) -> None:
        self.flashed = []

    def flash(self, msg):
        self.flashed.append(msg)

    def get(self, name):
        raise KeyError(name)


class FakeCtx:
    def __init__(self, npcs, meso: int) -> None:
        self.world = FakeWorld(npcs, meso)
        self.ui = FakeUI()
        self.assets = FakeAssets()
        self.windows = FakeWindows()


def _taxi_controller(meso: int):
    """造一个注册了 1000 金币票价目的地的出租车 NPC 控制器。"""
    travel.clear_teleports()
    travel.register_teleports("9900009", [("废弃都市", "103000000", 1000)])
    ctx = FakeCtx([FakeNPC("9900009", "出租车")], meso)
    ctrl = NpcDialogueController(ctx, {})
    warps = []
    ctrl.warp = warps.append
    return ctrl, ctx, warps


def test_taxi_label_shows_fare():
    """菜单链接把票价写进文案（乘客点之前知道价格）。"""
    ctrl, ctx, _ = _taxi_controller(1500)
    ctrl.try_talk()
    labels = [lab for lab, _ in ctx.ui.conv.shown[-1]]
    assert any("1000金币" in lab for lab in labels)


def test_taxi_click_pays_and_warps():
    """余额足够：点击扣票价并登记切图。"""
    ctrl, ctx, warps = _taxi_controller(1500)
    ctrl.try_talk()
    ctx.ui.conv.set_hit(0)
    ctrl.consume_click((0, 0))
    assert ctx.world.combat.meso == 500
    assert warps == ["103000000"]


def test_taxi_click_without_money_refuses():
    """余额不足：不扣钱、不切图，提示金币不足且菜单留在原地。"""
    ctrl, ctx, warps = _taxi_controller(999)
    ctrl.try_talk()
    ctx.ui.conv.set_hit(0)
    ctrl.consume_click((0, 0))
    assert ctx.world.combat.meso == 999
    assert warps == []
    assert ctx.windows.flashed == ["金币不足"]


def test_taxi_click_free_destination():
    """票价 0 的目的地不扣钱直接传送。"""
    travel.clear_teleports()
    travel.register_teleports("9900009", [("免费镇", "103000000", 0)])
    ctx = FakeCtx([FakeNPC("9900009", "出租车")], 0)
    ctrl = NpcDialogueController(ctx, {})
    warps = []
    ctrl.warp = warps.append
    ctrl.try_talk()
    ctx.ui.conv.set_hit(0)
    ctrl.consume_click((0, 0))
    assert ctx.world.combat.meso == 0
    assert warps == ["103000000"]


def test_ferry_and_orbis_ticket_sellers_registered():
    """渡轮售票员/车掌的真实 lua 注册官方线路：落点在对岸售票处，跨岛票价更贵。"""
    travel.clear_teleports()
    load_lua_quest_defs()
    assert travel.teleports_of("1032007") == [("天空之城", "200000100", 1500)]
    assert travel.teleports_of("2012000") == [("魔法密林", "101000300", 1500),
                                              ("玩具城", "220000100", 2000)]
    assert travel.teleports_of("2040000") == [("天空之城", "200000100", 2000)]


def test_five_star_taxis_sell_city_and_danger_routes():
    """五星级计程车：金银岛五站 2000（普通出租两倍）+ 一条高价危险专线。"""
    travel.clear_teleports()
    load_lua_quest_defs()
    cities = [("明珠港", "104000000", 2000), ("废弃都市", "103000000", 2000),
              ("射手村", "100000000", 2000), ("魔法密林", "101000000", 2000),
              ("勇士部落", "102000000", 2000)]
    assert travel.teleports_of("1002004") == cities + [("蚂蚁洞", "105050000", 3000)]
    assert travel.teleports_of("1032005") == cities + [("蘑菇王之墓", "105070002", 3000)]


def test_speed_taxi_drops_player_at_dragon_cave():
    """危险地带超高速计程车：只卖一条龙穴专线，票价 5000。"""
    travel.clear_teleports()
    load_lua_quest_defs()
    assert travel.teleports_of("2023000") == [("龙穴", "105090300", 5000)]


def test_subway_attendant_sells_no_route():
    """地铁站服务员不做传送：一号线在数据里是断头观光线。"""
    travel.clear_teleports()
    load_lua_quest_defs()
    assert travel.teleports_of("1052006") == []


def test_four_town_taxis_have_destinations():
    """四大城镇出租车 NPC 的真实 lua 各注册金银岛五站（含明珠港），票价 1000。"""
    travel.clear_teleports()
    load_lua_quest_defs()
    expected = {"明珠港": ("104000000", 1000), "废弃都市": ("103000000", 1000),
                "射手村": ("100000000", 1000), "魔法密林": ("101000000", 1000),
                "勇士部落": ("102000000", 1000)}
    for npc_id in ("1012000", "1022001", "1032000", "1052016"):
        dests = {lab: (mid, fare) for lab, mid, fare
                 in travel.teleports_of(npc_id, "999999999")}
        assert dests == expected
