-- 9120001（花子）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9120001_shop_1",
      name = "商店",
      items = {
        {item_id = "01002136", price = 100000},
        {item_id = "01032002", price = 110000},
        {item_id = "01040029", price = 110000},
        {item_id = "01060020", price = 110000},
        {item_id = "01051006", price = 110000},
        {item_id = "01072051", price = 25000},
        {item_id = "01072034", price = 25000},
        {item_id = "01072086", price = 25000},
        {item_id = "01072020", price = 30000},
        {item_id = "02070012", price = 100000},
        {item_id = "02070013", price = 100000},
      }
    },
  }
end

return M
