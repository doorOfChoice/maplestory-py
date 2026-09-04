-- 1012119（商店 NPC 托德）自定义任务、商店与 talk() 对话演示
local M = {}

function M.shops()
  return {
    {
      shop_id = "potions",
      name = "药水",
      items = {
        {item_id = "02000000", price = 50},
        {item_id = "02000003", price = 300},
        {item_id = "02000001", price = 30},
        {item_id = "02000002", price = 20},
        {item_id = "02000002", price = 20},
        {item_id = "02000002", price = 20},
        {item_id = "02000002", price = 20},
        {item_id = "02000002", price = 20},
      }
    },
    {
      shop_id = "weapons",
      name = "武器",
      items = {
        {item_id = "01452000", price = 500},
        {item_id = "01452002", price = 8000},
      }
    },
    {
      shop_id = "scrolls",
      name = "卷轴",
      items = {
        {item_id = "02340000", price = 150},
        {item_id = "02340002", price = 200},
        {item_id = "02340001", price = 100},
      }
    },
  }
end

-- talk() 完全接管对话（默认的任务/商店菜单不再出现），
-- 商店入口由链接自己调 open_shop() 登记（见 content/AGENTS.md 宿主函数表）。
-- 任务链：收集红药水 → 讨伐蓝宝 → 药水补货 → 托德的大订单，
-- 逐环解锁：接取链接的显隐由前一环是否已完成决定（运行时条件写在 show 里）。
function M.talk(ctx)
  local quests = {
    { qid = "c_1012119_1", title = "收集红药水", lv = 1,
      accepted = { "太好了！收集 10 个 #t2000000# 就来找我吧。",
                   "按 Q 查看任务日志。" },
      rewarded = { "这是你的奖励！" } },
    { qid = "c_1012119_2", title = "讨伐蓝宝", lv = 5, needs = "c_1012119_1",
      accepted = { "#b干得不错！#k接下来帮我把 #o100101# 清理 15 只，",
                   "它们最近太嚣张，吵得我睡不着。" },
      rewarded = { "噓，世界清净了。这几瓶 #t2000003# 算回礼。" } },
    { qid = "c_1012119_3", title = "药水补货", lv = 8, needs = "c_1012119_2",
      accepted = { "我的货架被搬空了！给我带回 5 瓶 #t2000003#，",
                   "店里也有，不过自己攒来的更有诚意。" },
      rewarded = { "上架！这批 #t2000003# 成色不错，你挑几瓶红药水走吧。" } },
    { qid = "c_1012119_4", title = "托德的大订单", lv = 12, needs = "c_1012119_3",
      accepted = { "有委托人下了笔大单子：#r30 个 #t2000000#、10 个 #t2000003##k。",
                   "办成了，佣金少不了你的。" },
      rewarded = { "漂亮！这是佣金，还有几张 #t2340000# 顺手送你。" } },
  }

  local function completable(qid)
    return function(c)
      if quest_state(qid) ~= "accepted" then return false end
      for _, e in ipairs(quest_completable(c.npc.id)) do
        if tostring(e.qid) == qid then return true end
      end
      return false
    end
  end

  local steps = {
    not_yet = { text = { "还差一些，继续加油！" } },
    busy    = { text = { "现在好像接不了，回头再看看你的等级吧。" } },
    chat    = { text = { "呵呵，看你装备渐佳，是个人物。" } },
  }
  local links = {}
  for _, q in ipairs(quests) do
    table.insert(links, {
      label = "接任务：" .. q.title,
      note  = q.lv,
      show  = function(c)
        return quest_state(q.qid) == "available"
                   and (q.needs == nil or quest_state(q.needs) == "completed")
      end,
      click = function(c)
        if accept_quest(q.qid) then return q.qid .. "_accepted" end
        return "busy"
      end,
    })
    table.insert(links, {
      label = "交付：" .. q.title,
      show  = completable(q.qid),
      click = function(c)
        if complete_quest(q.qid) then return q.qid .. "_rewarded" end
        return "not_yet"
      end,
    })
    steps[q.qid .. "_accepted"] = { text = q.accepted }
    steps[q.qid .. "_rewarded"] = { text = q.rewarded }
  end
  table.insert(links, { label = "商店", click = function(c) open_shop() end })
  table.insert(links, { label = "随便聊聊", click = function(c) return "chat" end })

  steps.greet = { text = { "哟，冒险者。要点什么？" }, links = links }
  return { title = "托德", start = "greet", steps = steps }
end

function M.entries(ctx)
  return {
    {
      type = "quest",
      name = "收集红药水",
      lvmin = 1,
      end_items = {{2000000, 10}},
      reward_exp = 200,
      reward_money = 1000,
      accept_lines = {"你要帮我收集 #t2000000# 吗？"},
      accept_yes = {"太好了！收集 10 个红药水就来找我吧。"},
      accept_no = {"好吧，改变主意了再来。"},
      complete_lines = {"你收集够了！要领取奖励吗？"},
      complete_yes = {"这是你的奖励！"},
      complete_stop = {"还差一些，继续加油！"},
      desc1 = "收集 10 个 #t2000000#，交给 #p1012119#。",
    },
    {
      type = "quest",
      name = "讨伐蓝宝",
      lvmin = 5,
      kills = { { 100101, 15 } },
      reward_exp = 600,
      reward_money = 2000,
      reward_items = { { 2000003, 3 } },
      accept_lines = { "上次的药水生意让我赚了不小一笔。现在，帮我解决点噪音问题？" },
      accept_yes = { "很好！在附近消灭 15 只 #o100101# 蓝宝，再来找我吧。" },
      accept_no = { "好吧，想通了随时来找我。" },
      complete_lines = { "噓，终于清净了。要领取回礼吗？" },
      complete_yes = { "这几瓶 #t2000003# 算回礼，别客气。" },
      complete_stop = { "蓝宝还没打够？别想糊弄我。" },
      desc1 = "讨伐 15 只 #o100101#，回报 #p1012119#。",
    },
    {
      type = "quest",
      name = "药水补货",
      lvmin = 8,
      end_items = { { 2000003, 5 } },
      reward_exp = 900,
      reward_money = 3000,
      reward_items = { { 2000000, 10 } },
      accept_lines = { "我的货架被搬空了！帮我凑一批 #t2000003# 怎么样？" },
      accept_yes = { "带回 5 瓶 #t2000003# 就行。店里也有，不过自己攒来的更有诚意。" },
      accept_no = { "好吧，改主意了再来。" },
      complete_lines = { "上架！要换点红药水走吗？" },
      complete_yes = { "这批 #t2000003# 成色不错，你挑 10 瓶 #t2000000# 走吧。" },
      complete_stop = { "药水还不够，别逗我笑。" },
      desc1 = "收集 5 个 #t2000003#，交给 #p1012119#。",
    },
    {
      type = "quest",
      name = "托德的大订单",
      lvmin = 12,
      end_items = { { 2000000, 30 }, { 2000003, 10 } },
      reward_exp = 2000,
      reward_money = 8888,
      reward_items = { { 2340000, 3 } },
      accept_lines = { "有委托人下了笔大单子，我看你是唯一吃得下的人。" },
      accept_yes = { "#r30 个 #t2000000#、10 个 #t2000003##k，凑齐了来找我拿佣金。" },
      accept_no = { "也是，这单子确实不小。想通了再来。" },
      complete_lines = { "完美交付！佣金结一下？" },
      complete_yes = { "这是佣金，还有几张 #t2340000# 顺手送你。" },
      complete_stop = { "数量差得远呢，这可是大客户的单子。" },
      desc1 = "为 #p1012119# 的大订单备货：30 个 #t2000000#、10 个 #t2000003#。",
    },
  }
end

return M
