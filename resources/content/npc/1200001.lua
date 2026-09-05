-- 1200001（噗诺晕）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1200001_shop_1",
      name = "商店",
      items = {
        {item_id = "01442000", price = 3000},
        {item_id = "01442006", price = 8000},
        {item_id = "01442007", price = 12000},
        {item_id = "01040002", price = 50},
        {item_id = "01040006", price = 50},
        {item_id = "01040010", price = 50},
        {item_id = "01041002", price = 50},
        {item_id = "01041006", price = 50},
        {item_id = "01041010", price = 50},
        {item_id = "01041011", price = 50},
        {item_id = "01060002", price = 50},
        {item_id = "01060006", price = 50},
        {item_id = "01061002", price = 50},
        {item_id = "01061008", price = 50},
        {item_id = "01072001", price = 50},
        {item_id = "01072005", price = 50},
      }
    },
  }
end

return M
