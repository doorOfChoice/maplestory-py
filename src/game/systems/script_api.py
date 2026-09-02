"""宿主 API：把可交给 Lua 调用的「名字 → 可调用对象」打包成一张注册表。

内容脚本（content/*.lua）只引用这些名字，不 import 任何游戏模块；因此改台词/流程
只动 .lua，自定义发奖数值直接写在 Lua（give_reward）。所有函数闭包持有宿主上下文
``ctx``（SimpleNamespace）：
- 转职：can_advance() / advance_job()（改真身并置 ctx.advanced）
- 发奖（当 ctx 携带 world 时注册）：give_reward(exp, meso, items)——直接给玩家发奖励，
  items 为 [[item_id, count], ...]，负数=收回
- 任务（当 ctx 携带 world/quest_defs 时注册）：quest_available / quest_completable /
  quest_state / accept_quest / complete_quest / quest_info（薄封装，复用 quests.py 逻辑）
- 商店（当 ctx 携带 world 时注册）：get_shop_items(shop_id) / shop_buy(item_id, count) /
  shop_sell(item_id, count)

安全：宿主运行时禁用 os/io/package/dofile/loadfile，脚本为仓库内可信文本。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

# 任务状态可被 Lua 读到的字符串 → 映射到 quests.Q_* 常量
_STATE_ALIASES = {"available": "available", "accepted": "accepted", "completed": "completed"}


def _quest_state_name(state: str) -> str:
    return _STATE_ALIASES.get(state, state)


def make_globals(ctx: Any) -> Dict[str, Callable]:
    """按 ctx 拥有的字段封装可注册的 Lua 全局函数。"""
    from game.core.jobs import can_advance as _can_advance

    def can_advance() -> bool:
        """判定当前 ctx 的玩家能否转职为 ctx.jobdef。"""
        return _can_advance(ctx.player, ctx.jobdef)

    def advance_job() -> None:
        """触发转职：改真身职业并附带技能/武器，置 ctx.advanced。"""
        ctx.player.advance_to(ctx.jobdef.code, ctx.assets)
        ctx.advanced = True

    globals_: Dict[str, Callable] = {"can_advance": can_advance, "advance_job": advance_job}

    # 发奖：仅当 ctx 携带世界时注册（转职上下文无 world → 不注册，调用即报错）
    world = getattr(ctx, "world", None)
    if world is not None:
        from game.systems.quests import QuestLog

        def give_reward(exp=0, meso=0, items=None) -> bool:
            """按 Lua 指定直接发奖：exp/金币/物品；物品负数量=收回。"""
            player = world.player
            if items is not None:
                for i in range(1, len(items) + 1):
                    item_id, count = items[i][1], items[i][2]
                    if count < 0:
                        QuestLog._take_item(player, int(item_id), -int(count))
                    else:
                        QuestLog._give_item(player, int(item_id), int(count))
            if exp:
                player.gain_exp(int(exp))
            if meso:
                world.combat.meso += int(meso)
            return True

        globals_["give_reward"] = give_reward

    # 任务相关：仅当 ctx 携带世界/任务表时注册（转职上下文无需，避免死代码）
    defs = getattr(ctx, "quest_defs", None)
    if world is not None and defs is not None:
        quests = world.player.quests

        def quest_available(npc_id) -> List[dict]:
            from game.systems.quests import collect_npc_quests, NpcQuest
            # 只取可接取/可交付，转成 Lua 字典数组（qid/title/level/state）
            items = collect_npc_quests(defs, quests, str(npc_id), world.player)
            return [{"qid": it.qid, "title": it.title, "level": it.level, "state": it.state}
                    for it in items]

        def quest_completable(npc_id) -> List[dict]:
            from game.systems.quests import collect_npc_quests
            items = collect_npc_quests(defs, quests, str(npc_id), world.player)
            return [{"qid": it.qid, "title": it.title, "level": it.level, "state": it.state}
                    for it in items if it.state == "complete"]

        def quest_state(qid) -> str:
            if quests.is_completed(str(qid)):
                return _quest_state_name("completed")
            if quests.is_accepted(str(qid)):
                return _quest_state_name("accepted")
            return _quest_state_name("available")

        def accept_quest(qid) -> bool:
            return quests.accept(str(qid), world.player)

        def complete_quest(qid) -> bool:
            return quests.complete(str(qid), world.player, world.combat, world.assets,
                                   getattr(world, "audio", None))

        def quest_info(qid) -> dict:
            d = defs.get(str(qid))
            if d is None:
                return {}
            return {"name": d.name, "reward_exp": d.reward_exp,
                    "reward_money": d.reward_money}

        globals_["quest_available"] = quest_available
        globals_["quest_completable"] = quest_completable
        globals_["quest_state"] = quest_state
        globals_["accept_quest"] = accept_quest
        globals_["complete_quest"] = complete_quest
        globals_["quest_info"] = quest_info

    # 商店相关：仅当 ctx 携带 world 时注册（与任务函数相同条件）
    if world is not None:
        from game.systems import shop as shop_mod

        def get_shop_items(shop_id: str) -> List[dict]:
            """获取指定商店的货架物品列表。"""
            items = shop_mod.SHOPS.get(shop_id, [])
            return [{"item_id": iid, "price": shop_mod.item_price(iid, world.assets) or 0}
                    for iid in items]

        def shop_buy(item_id: str, count: int = 1) -> bool:
            """购买物品。需先通过 open_shop 打开商店。"""
            shop_id = getattr(ctx, "_current_shop", None)
            if shop_id is None:
                return False
            price = shop_mod.item_price(item_id, world.assets) or 0
            ok, _meso = shop_mod.buy(shop_id, item_id, world.combat.meso,
                                     world.player.inventory, price=price, count=count)
            if ok:
                world.combat.meso = _meso
            return ok

        def shop_sell(item_id: str, count: int = 1) -> bool:
            """出售物品。需先通过 open_shop 打开商店。"""
            shop_id = getattr(ctx, "_current_shop", None)
            if shop_id is None:
                return False
            inv = world.player.inventory
            for bucket in (inv.consumes, inv.etcs):
                for key, item in list(bucket.items()):
                    if item.id == item_id:
                        sell_count = min(count, item.count)
                        price = shop_mod.item_price(item_id, world.assets) or 0
                        gain = shop_mod.sell_price(price) * sell_count
                        world.combat.meso += gain
                        item.count -= sell_count
                        if item.count <= 0:
                            del bucket[key]
                        return True
            for i, item in enumerate(inv.equips):
                if item.id == item_id:
                    price = shop_mod.item_price(item_id, world.assets) or 0
                    gain = shop_mod.sell_price(price)
                    world.combat.meso += gain
                    inv.equips.pop(i)
                    return True
            return False

        globals_["get_shop_items"] = get_shop_items
        globals_["shop_buy"] = shop_buy
        globals_["shop_sell"] = shop_sell

    return globals_