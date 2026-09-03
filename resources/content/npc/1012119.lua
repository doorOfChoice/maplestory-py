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

-- talk() 完全接管对话（默认的任务/商店菜单不再出现）。
-- 当前宿主未提供 open_shop，故本演示暂无商店入口（见 content/AGENTS.md「未提供」）。
function M.talk(ctx)
  local QID = "c_1012119_1"
  return {
    title = "托德",
    start = "greet",
    steps = {
      greet = {
        text = { "哟，冒险者。要点什么？" },
        links = {
          { label = "接任务：收集红药水",
            show  = function(c) return quest_state(QID) == "available" end,
            click = function(c) if accept_quest(QID) then return "accepted" end
                                 return "busy" end },
          { label = "交付：收集红药水",
            show  = function(c) return quest_state(QID) == "accepted"
                                      and #quest_completable(c.npc.id) > 0 end,
            click = function(c) if complete_quest(QID) then return "rewarded" end
                                 return "not_yet" end },
          { label = "随便聊聊",
            click = function(c) return "chat" end },
        },
      },
      accepted = { text = { "太好了！收集 10 个 #t2000000# 就来找我吧。",
                           "按 Q 查看任务日志。" } },
      rewarded = { text = { "这是你的奖励！" } },
      not_yet  = { text = { "还差一些，继续加油！" } },
      busy     = { text = { "现在好像接不了，回头再看看你的等级吧。" } },
      chat     = { text = { "呵呵，看你装备渐佳，是个人物。" } },
    },
  }
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
    },
  }
end

return M
