-- 9270027（艾尔文）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9270027_shop_1",
      name = "商店",
      items = {
        {item_id = "02022214", price = 3200},
        {item_id = "02022211", price = 6400},
        {item_id = "02022210", price = 3200},
        {item_id = "02022209", price = 1600},
        {item_id = "02022208", price = 1000},
        {item_id = "02022207", price = 2600},
        {item_id = "02022206", price = 2200},
        {item_id = "02022205", price = 1800},
        {item_id = "02022204", price = 1200},
        {item_id = "02022203", price = 800},
      }
    },
  }
end

return M
