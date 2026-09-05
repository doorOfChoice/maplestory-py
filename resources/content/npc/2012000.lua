-- 2012000（天空之城售票处 售票员）渡轮线路：开往魔法森林 / 玩具城
local M = {}

function M.entries(ctx)
  return {
    { type = "teleport", label = "魔法密林", map = "101000300", fare = 1500 },
    { type = "teleport", label = "玩具城",   map = "220000100", fare = 2000 },
  }
end

return M
