-- 9120000（阿利博士）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9120000_shop_1",
      name = "商店",
      items = {
        {item_id = "01472008", price = 250000},
        {item_id = "01312013", price = 100000},
        {item_id = "01322012", price = 15000},
        {item_id = "01402009", price = 30000},
        {item_id = "01432008", price = 150000},
        {item_id = "01402010", price = 150000},
        {item_id = "01462006", price = 500000},
        {item_id = "01302021", price = 1250000},
        {item_id = "01302022", price = 80000},
        {item_id = "01332024", price = 2000000},
        {item_id = "01382011", price = 2000000},
        {item_id = "02070000", price = 500},
      }
    },
  }
end

return M
