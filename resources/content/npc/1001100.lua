-- 1001100（米娜）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1001100_shop_1",
      name = "商店",
      items = {
        {item_id = "02000000", price = 30},
        {item_id = "02061000", price = 1},
        {item_id = "02060000", price = 1},
        {item_id = "02030001", price = 500},
        {item_id = "02030000", price = 400},
        {item_id = "02020028", price = 3000},
        {item_id = "02010004", price = 180},
        {item_id = "02010003", price = 60},
        {item_id = "02010001", price = 106},
        {item_id = "02010002", price = 50},
        {item_id = "02010000", price = 30},
        {item_id = "02002005", price = 500},
        {item_id = "02002004", price = 500},
        {item_id = "02002002", price = 500},
        {item_id = "02002001", price = 400},
        {item_id = "02002000", price = 500},
        {item_id = "02000006", price = 385},
        {item_id = "02000003", price = 150},
        {item_id = "02000002", price = 280},
        {item_id = "02000001", price = 150},
        {item_id = "02330000", price = 800},
        {item_id = "02070000", price = 500},
      }
    },
  }
end

return M
