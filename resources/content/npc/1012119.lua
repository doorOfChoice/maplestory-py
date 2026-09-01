-- 1012119（商店 NPC 托德）自定义任务示例
local M = {}

function M.quests(ctx)
  return {
    {
      name = "收集红药水",
      lvmin = 1,
      end_items = {{2000000, 10}},  -- 收集 10 个红药水
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