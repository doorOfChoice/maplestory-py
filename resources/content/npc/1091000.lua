-- 1091000（摩根）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1091000_shop_1",
      name = "商店",
      items = {
        {item_id = "01322007", price = 6000},
        {item_id = "01302007", price = 3000},
        {item_id = "01442004", price = 24000},
        {item_id = "01482004", price = 52000},
        {item_id = "01482003", price = 20000},
        {item_id = "01482002", price = 10000},
        {item_id = "01482001", price = 6000},
        {item_id = "01482000", price = 3000},
        {item_id = "01492004", price = 50000},
        {item_id = "01492003", price = 22000},
        {item_id = "01492002", price = 10000},
        {item_id = "01492001", price = 6000},
        {item_id = "01492000", price = 3000},
      }
    },
  }
end

return M
