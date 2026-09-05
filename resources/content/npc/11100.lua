-- 11100（露茜）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "11100_shop_1",
      name = "商店",
      items = {
        {item_id = "02000000", price = 30},
        {item_id = "02000001", price = 150},
        {item_id = "02000002", price = 280},
        {item_id = "02010000", price = 30},
        {item_id = "02010002", price = 50},
      }
    },
  }
end

return M
