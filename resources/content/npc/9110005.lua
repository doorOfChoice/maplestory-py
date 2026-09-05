-- 9110005（健二）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9110005_shop_1",
      name = "商店",
      items = {
        {item_id = "02022025", price = 4200},
        {item_id = "02022024", price = 2000},
      }
    },
  }
end

return M
