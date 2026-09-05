-- 2010004（未散 中等兵）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "2010004_shop_1",
      name = "商店",
      items = {
        {item_id = "02260000", price = 1000},
        {item_id = "02120000", price = 30},
      }
    },
  }
end

return M
