-- 1032005（魔法森林 五星级计程车）：四大城市双倍票价 + 蘑菇王之墓专线
local M = {}

function M.entries(ctx)
  return {
    { type = "teleport", label = "明珠港", map = "104000000", fare = 2000 },
    { type = "teleport", label = "废弃都市", map = "103000000", fare = 2000 },
    { type = "teleport", label = "射手村",   map = "100000000", fare = 2000 },
    { type = "teleport", label = "魔法密林", map = "101000000", fare = 2000 },
    { type = "teleport", label = "勇士部落", map = "102000000", fare = 2000 },
    { type = "teleport", label = "蘑菇王之墓", map = "105070002", fare = 3000 },
  }
end

return M
