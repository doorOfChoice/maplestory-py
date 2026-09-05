-- 1001000（赛尔文）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1001000_shop_1",
      name = "商店",
      items = {
        {item_id = "01332007", price = 1000},
        {item_id = "01312000", price = 3000},
        {item_id = "01302007", price = 3000},
        {item_id = "01322005", price = 50},
        {item_id = "01312004", price = 50},
        {item_id = "01302000", price = 50},
      }
    },
  }
end

return M
