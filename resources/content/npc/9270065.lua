-- 9270065（阿里　）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9270065_shop_1",
      name = "商店",
      items = {
        {item_id = "02022476", price = 4200},
        {item_id = "02022477", price = 9200},
        {item_id = "02022478", price = 3200},
        {item_id = "02022479", price = 3800},
        {item_id = "02022480", price = 12000},
        {item_id = "02022203", price = 800},
        {item_id = "02022204", price = 1200},
        {item_id = "02022205", price = 1800},
        {item_id = "02022206", price = 2200},
        {item_id = "02022207", price = 2600},
        {item_id = "02022208", price = 1000},
        {item_id = "02022209", price = 1600},
        {item_id = "02022210", price = 3200},
        {item_id = "02022211", price = 6400},
        {item_id = "02022214", price = 3200},
        {item_id = "02022215", price = 6800},
        {item_id = "02050000", price = 200},
        {item_id = "02050001", price = 200},
        {item_id = "02050002", price = 300},
        {item_id = "02050003", price = 500},
        {item_id = "02030000", price = 400},
        {item_id = "02060000", price = 1},
        {item_id = "02061000", price = 1},
      }
    },
  }
end

return M
