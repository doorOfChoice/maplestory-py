-- 2040000（玩具城售票处 车掌）渡轮线路：开往天空之城
local M = {}

function M.entries(ctx)
  return {
    { type = "teleport", label = "天空之城", map = "200000100", fare = 2000 },
  }
end

return M
