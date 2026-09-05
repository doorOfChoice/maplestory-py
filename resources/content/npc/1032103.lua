-- 1032103（艾摩斯）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1032103_shop_1",
      name = "商店",
      items = {
        {item_id = "02040000", price = 35000},
        {item_id = "02040400", price = 35000},
        {item_id = "02040600", price = 35000},
        {item_id = "02040700", price = 35000},
        {item_id = "02040300", price = 35000},
        {item_id = "02044500", price = 70000},
        {item_id = "02044600", price = 70000},
        {item_id = "02043800", price = 70000},
      }
    },
  }
end

return M
