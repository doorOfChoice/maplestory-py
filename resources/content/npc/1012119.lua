-- 1012119（商店 NPC 托德）自定义任务、商店与 talk() 对话演示
local M = {}

function M.shops()
  return {
    {
      shop_id = "potions",
      name = "药水",
      items = {
        {item_id = "02000002", price = 20},
        {item_id = "02000001", price = 30},
        {item_id = "02000000", price = 50},
        {item_id = "02000003", price = 300},
        {item_id = "02000004", price = 500},
        {item_id = "02000005", price = 1000},
        {item_id = "02000006", price = 1500},
        {item_id = "02000015", price = 600},
        {item_id = "02000016", price = 400},
        {item_id = "02000017", price = 800},
        {item_id = "02000018", price = 1800},
      }
    },
    {
      shop_id = "cures",
      name = "状态药",
      items = {
        {item_id = "02050000", price = 100},
        {item_id = "02050001", price = 100},
        {item_id = "02050002", price = 100},
        {item_id = "02050003", price = 150},
        {item_id = "02050004", price = 300},
      }
    },
    {
      shop_id = "foods",
      name = "点心",
      items = {
        {item_id = "02022000", price = 100},
        {item_id = "02022002", price = 150},
        {item_id = "02022003", price = 300},
        {item_id = "02022016", price = 1000},
        {item_id = "02022024", price = 200},
        {item_id = "02022131", price = 500},
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

-- ═══ 任务：数值 + 台词的唯一事实来源（qid 按顺序生成 c_1012119_<序号>）═══
-- prereq/lvmin 驱动 QuestLog 判定与 quest 链接显隐；accept_yes/complete_yes/
-- complete_stop 三个 Say 槽既是默认子会话文案，也是 talk() 展开后的终态步文案。
function M.entries(ctx)
  return {
    {
      type = "quest",
      name = "收集红药水",
      lvmin = 1,
      end_items = {{2000000, 10}},
      reward_exp = 200,
      reward_money = 1000,
      accept_yes = {"太好了！收集 10 个 #t2000000# 就来找我吧。",
                    "按 Q 查看任务日志。"},
      complete_yes = {"这是你的奖励！"},
      complete_stop = {"还差一些，继续加油！"},
      desc1 = "收集 10 个 #t2000000#，交给 #p1012119#。",
    },
    {
      type = "quest",
      name = "讨伐蓝宝",
      lvmin = 5,
      prereq = { { "c_1012119_1", 2 } },
      kills = { { 100101, 15 } },
      reward_exp = 600,
      reward_money = 2000,
      reward_items = { { 2000003, 3 } },
      accept_yes = { "#b干得不错！#k接下来帮我把 #o100101# 清理 15 只，",
                     "它们最近太嚣张，吵得我睡不着。" },
      complete_yes = { "噓，世界清净了。这几瓶 #t2000003# 算回礼。" },
      complete_stop = { "蓝宝还没打够？别想糊弄我。" },
      desc1 = "讨伐 15 只 #o100101#，回报 #p1012119#。",
    },
    {
      type = "quest",
      name = "药水补货",
      lvmin = 8,
      prereq = { { "c_1012119_2", 2 } },
      end_items = { { 2000003, 5 } },
      reward_exp = 900,
      reward_money = 3000,
      reward_items = { { 2000000, 10 } },
      accept_yes = { "我的货架被搬空了！给我带回 5 瓶 #t2000003#，",
                     "店里也有，不过自己攒来的更有诚意。" },
      complete_yes = { "上架！这批 #t2000003# 成色不错，你挑几瓶红药水走吧。" },
      complete_stop = { "药水还不够，别逗我笑。" },
      desc1 = "收集 5 个 #t2000003#，交给 #p1012119#。",
    },
    {
      type = "quest",
      name = "托德的大订单",
      lvmin = 12,
      prereq = { { "c_1012119_3", 2 } },
      end_items = { { 2000000, 30 }, { 2000003, 10 } },
      reward_exp = 2000,
      reward_money = 8888,
      reward_items = { { 2340000, 3 } },
      accept_yes = { "有委托人下了笔大单子：#r30 个 #t2000000#、10 个 #t2000003##k。",
                     "办成了，佣金少不了你的。" },
      complete_yes = { "漂亮！这是佣金，还有几张 #t2340000# 顺手送你。" },
      complete_stop = { "数量差得远呢，这可是大客户的单子。" },
      desc1 = "为 #p1012119# 的大订单备货：30 个 #t2000000#、10 个 #t2000003#。",
    },
  }
end

-- talk() 声明式接管：任务/商店链接交宿主展开（type 判别，见 content/AGENTS.md），
-- takeover = "on_business"：可接/可交付都没有时（没开始、或全干完了）让位，
-- 由宿主路由直开商店。任务链显隐的唯一事实来源是 entries() 的 prereq/lvmin。
function M.talk(ctx)
  return {
    title = "托德",
    start = "greet",
    takeover = "on_business",
    steps = {
      greet = {
        text = { "哟，冒险者。要点什么？" },
        links = {
          { type = "quest", qid = "c_1012119_1" },
          { type = "quest", qid = "c_1012119_2" },
          { type = "quest", qid = "c_1012119_3" },
          { type = "quest", qid = "c_1012119_4" },
          { type = "shop" },
          { label = "随便聊聊", click = function(c) return "chat" end },
        },
      },
      chat = { text = { "呵呵，看你装备渐佳，是个人物。" } },
      busy = { text = { "现在好像接不了，回头再看看你的等级吧。" } },
    },
  }
end

return M
