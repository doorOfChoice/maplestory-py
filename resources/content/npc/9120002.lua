-- 9120002（小优）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9120002_shop_1",
      name = "商店",
      items = {
        {item_id = "02070000", price = 500},
        {item_id = "02020014", price = 8100},
        {item_id = "02022002", price = 1000},
        {item_id = "02001002", price = 4000},
        {item_id = "02000006", price = 620},
        {item_id = "02000003", price = 200},
        {item_id = "02020012", price = 4500},
        {item_id = "02001001", price = 2300},
        {item_id = "02000002", price = 320},
        {item_id = "02000001", price = 160},
        {item_id = "02060003", price = 40},
      }
    },
  }
end

return M
