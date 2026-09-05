-- 9110007（元泰）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9110007_shop_1",
      name = "商店",
      items = {
        {item_id = "02022015", price = 12000},
        {item_id = "02022020", price = 550},
        {item_id = "02022019", price = 850},
        {item_id = "02022018", price = 1600},
        {item_id = "02022017", price = 1100},
      }
    },
  }
end

return M
