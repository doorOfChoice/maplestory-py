-- 1061001（24小时 排挡）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1061001_shop_1",
      name = "商店",
      items = {
        {item_id = "02020001", price = 150},
        {item_id = "02020005", price = 320},
        {item_id = "02020003", price = 225},
        {item_id = "02020004", price = 225},
        {item_id = "02022003", price = 770},
        {item_id = "02020000", price = 420},
        {item_id = "02022000", price = 1155},
        {item_id = "02020002", price = 320},
        {item_id = "02060000", price = 1},
        {item_id = "02061000", price = 1},
        {item_id = "02030000", price = 400},
        {item_id = "02070000", price = 500},
        {item_id = "02330000", price = 800},
      }
    },
  }
end

return M
