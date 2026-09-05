-- 9201060（米琪）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9201060_shop_1",
      name = "商店",
      items = {
        {item_id = "02000000", price = 30},
        {item_id = "02000001", price = 150},
        {item_id = "02000002", price = 280},
        {item_id = "02000003", price = 150},
        {item_id = "02000006", price = 385},
        {item_id = "02002016", price = 5000},
        {item_id = "02002017", price = 7500},
        {item_id = "02002018", price = 5000},
        {item_id = "02002019", price = 5000},
        {item_id = "02002020", price = 6800},
        {item_id = "02002021", price = 6800},
        {item_id = "02002022", price = 8100},
        {item_id = "02002023", price = 13800},
        {item_id = "02002024", price = 1500},
        {item_id = "02002025", price = 1500},
        {item_id = "02010000", price = 30},
        {item_id = "02010002", price = 50},
        {item_id = "02010001", price = 150},
        {item_id = "02010003", price = 100},
        {item_id = "02010004", price = 180},
        {item_id = "02022189", price = 1000},
        {item_id = "02022191", price = 1000},
        {item_id = "02022192", price = 600},
        {item_id = "02022003", price = 770},
        {item_id = "02022000", price = 1150},
        {item_id = "02001000", price = 3200},
        {item_id = "02001001", price = 2300},
        {item_id = "02001002", price = 4000},
        {item_id = "02022190", price = 3000},
        {item_id = "02020012", price = 4500},
        {item_id = "02020013", price = 5600},
        {item_id = "02020014", price = 8100},
        {item_id = "02020015", price = 10200},
        {item_id = "02022195", price = 15000},
        {item_id = "02030000", price = 400},
        {item_id = "02060000", price = 1},
        {item_id = "02061000", price = 1},
        {item_id = "02070000", price = 500},
        {item_id = "02330000", price = 800},
      }
    },
  }
end

return M
