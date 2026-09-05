-- 2023000（危险地带超高速计程车，雪域/玩具城/神木村）：一条龙穴专线
local M = {}

function M.entries(ctx)
  return {
    { type = "teleport", label = "龙穴", map = "105090300", fare = 5000 },
  }
end

return M
