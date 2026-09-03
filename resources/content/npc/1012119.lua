-- 1012119（商店 NPC 托德）自定义任务与商店示例
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
