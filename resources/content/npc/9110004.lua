-- 9110004（基得）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9110004_shop_1",
      name = "商店",
      items = {
        {item_id = "02022023", price = 1350},
        {item_id = "02022014", price = 650},
      }
    },
  }
end

return M
