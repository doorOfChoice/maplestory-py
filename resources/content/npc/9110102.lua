-- 9110102（伊西拉兹）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9110102_shop_1",
      name = "商店",
      items = {
        {item_id = "02000000", price = 30},
        {item_id = "02000001", price = 150},
        {item_id = "02000002", price = 280},
        {item_id = "02000003", price = 150},
        {item_id = "02002000", price = 400},
        {item_id = "02002001", price = 400},
        {item_id = "02002002", price = 400},
        {item_id = "02002003", price = 400},
        {item_id = "02002004", price = 500},
        {item_id = "02002005", price = 400},
        {item_id = "02001000", price = 3200},
        {item_id = "02001001", price = 2300},
        {item_id = "02001002", price = 4000},
        {item_id = "02010000", price = 50},
        {item_id = "02010001", price = 150},
        {item_id = "02010002", price = 50},
        {item_id = "02010003", price = 60},
        {item_id = "02010004", price = 180},
        {item_id = "02020012", price = 4680},
        {item_id = "02020013", price = 5824},
        {item_id = "02020014", price = 8424},
        {item_id = "02020015", price = 10608},
        {item_id = "02022003", price = 770},
        {item_id = "02022000", price = 1155},
        {item_id = "02060000", price = 1},
        {item_id = "02061000", price = 1},
        {item_id = "02060001", price = 10},
        {item_id = "02061001", price = 10},
        {item_id = "02030000", price = 250},
        {item_id = "02330000", price = 800},
        {item_id = "02070000", price = 500},
      }
    },
  }
end

return M
