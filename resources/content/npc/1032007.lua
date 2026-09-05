-- 1032007（魔法森林码头 售票员）渡轮线路：买了票就可以乘坐开往天空之城的船
local M = {}

function M.entries(ctx)
  return {
    { type = "teleport", label = "天空之城", map = "200000100", fare = 1500 },
  }
end

return M
