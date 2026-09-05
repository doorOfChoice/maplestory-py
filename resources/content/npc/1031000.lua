-- 1031000（妖精 佛罗拉）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1031000_shop_1",
      name = "商店",
      items = {
        {item_id = "01372005", price = 2000},
        {item_id = "01372006", price = 5000},
        {item_id = "01372002", price = 9000},
        {item_id = "01372004", price = 18000},
        {item_id = "01372003", price = 38000},
        {item_id = "01382003", price = 6000},
        {item_id = "01382005", price = 6000},
        {item_id = "01382004", price = 10000},
        {item_id = "01382002", price = 20000},
        {item_id = "01322002", price = 10000},
      }
    },
  }
end

return M
