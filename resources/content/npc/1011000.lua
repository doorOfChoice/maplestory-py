-- 1011000（克尔）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1011000_shop_1",
      name = "商店",
      items = {
        {item_id = "01452002", price = 3000},
        {item_id = "01452003", price = 6000},
        {item_id = "01452001", price = 10000},
        {item_id = "01452000", price = 20000},
        {item_id = "01452005", price = 40000},
        {item_id = "01462001", price = 4000},
        {item_id = "01462002", price = 8000},
        {item_id = "01462003", price = 12000},
        {item_id = "01462000", price = 30000},
        {item_id = "01462004", price = 40000},
        {item_id = "01302007", price = 3000},
        {item_id = "01322007", price = 6000},
        {item_id = "01322008", price = 12000},
        {item_id = "01422004", price = 20000},
        {item_id = "01442004", price = 24000},
      }
    },
  }
end

return M
