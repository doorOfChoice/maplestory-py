-- 1091001（罗德斯）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1091001_shop_1",
      name = "商店",
      items = {
        {item_id = "01072288", price = 8000},
        {item_id = "01072285", price = 5000},
        {item_id = "01052107", price = 60000},
        {item_id = "01052104", price = 30000},
        {item_id = "01052101", price = 16000},
        {item_id = "01052098", price = 8000},
        {item_id = "01052095", price = 4000},
        {item_id = "01002619", price = 20000},
        {item_id = "01002616", price = 12000},
        {item_id = "01002613", price = 4000},
        {item_id = "01002610", price = 900},
      }
    },
  }
end

return M
