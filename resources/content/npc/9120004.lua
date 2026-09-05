-- 9120004（灰源）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9120004_shop_1",
      name = "商店",
      items = {
        {item_id = "02030010", price = 500},
        {item_id = "02030009", price = 500},
        {item_id = "02030008", price = 400},
        {item_id = "01050100", price = 30000},
        {item_id = "02070000", price = 500},
      }
    },
  }
end

return M
