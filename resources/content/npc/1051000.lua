-- 1051000（曼斯塔）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1051000_shop_1",
      name = "商店",
      items = {
        {item_id = "01472000", price = 3000},
        {item_id = "01442000", price = 3000},
        {item_id = "01432001", price = 7000},
        {item_id = "01432000", price = 3000},
        {item_id = "01422000", price = 3000},
        {item_id = "01412001", price = 3000},
        {item_id = "01402001", price = 3000},
        {item_id = "01322009", price = 20000},
        {item_id = "01332009", price = 42000},
        {item_id = "01332012", price = 40000},
        {item_id = "01332004", price = 38000},
        {item_id = "01332010", price = 22000},
        {item_id = "01332013", price = 15000},
        {item_id = "01332008", price = 10000},
        {item_id = "01332002", price = 8000},
        {item_id = "01332006", price = 7000},
        {item_id = "01332000", price = 4000},
        {item_id = "01302007", price = 3000},
      }
    },
  }
end

return M
