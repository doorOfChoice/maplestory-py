-- 1012100（转职教官 赫丽娜）新手任务
local M = {}

function M.entries(ctx)
  return {
    {
      type = "quest",
      name = "新手入门1",
      lvmin = 1,
      jobs = { 0 },
      kills = { { 100101, 10 } },  -- 击杀 10 只蓝宝
      reward_exp = 200,
      reward_money = 200,
      accept_lines = { "欢迎来到冒险世界！作为你的转职教官，我先教你基础的战斗。" },
      accept_yes = { "很好！在附近消灭 10 只 #o100101# 蓝宝，再来找我吧。" },
      accept_no = { "好吧，想学战斗了随时来找我。" },
      complete_lines = { "你击杀了 10 只蓝宝，干得不错！要领取新手奖励吗？" },
      complete_yes = { "这是你的新手奖励，好好利用它继续成长吧！" },
      complete_stop = { "还差一些蓝宝，继续加油！" },
    },
    {
      type = "quest",
      name = "新手入门2",
      lvmin = 1,
      jobs = { 0 },
      kills = { { 100101, 10 } },  -- 击杀 10 只蓝宝
      reward_exp = 200,
      reward_money = 200,
      accept_lines = { "欢迎来到冒险世界！作为你的转职教官，我先教你基础的战斗。" },
      accept_yes = { "很好！在附近消灭 10 只 #o100101# 蓝宝，再来找我吧。" },
      accept_no = { "好吧，想学战斗了随时来找我。" },
      complete_lines = { "你击杀了 10 只蓝宝，干得不错！要领取新手奖励吗？" },
      complete_yes = { "这是你的新手奖励，好好利用它继续成长吧！" },
      complete_stop = { "还差一些蓝宝，继续加油！" },
    },
  }
end

return M
