-- 1052016（废弃都市 出租车）传送条目：目的地含本镇，运行时按当前地图剔除
local M = {}

function M.entries(ctx)
  return {
    { type = "teleport", label = "废弃都市", map = "103000000" },
    { type = "teleport", label = "射手村",   map = "100000000" },
    { type = "teleport", label = "魔法密林", map = "101000000" },
    { type = "teleport", label = "勇士部落", map = "102000000" },
  }
end

return M
