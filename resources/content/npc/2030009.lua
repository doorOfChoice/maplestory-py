-- 2030009（格里巴）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "2030009_shop_1",
      name = "商店",
      items = {
        {item_id = "02002011", price = 1200},
        {item_id = "02330000", price = 800},
        {item_id = "02070000", price = 500},
        {item_id = "02061000", price = 1},
        {item_id = "02060000", price = 1},
        {item_id = "02030000", price = 400},
        {item_id = "02020015", price = 10608},
        {item_id = "02020014", price = 8424},
        {item_id = "02020013", price = 5824},
        {item_id = "02020012", price = 4680},
        {item_id = "02022000", price = 1155},
        {item_id = "02022003", price = 770},
        {item_id = "02020006", price = 551},
        {item_id = "02020004", price = 468},
        {item_id = "02020003", price = 468},
        {item_id = "02020001", price = 228},
        {item_id = "02010004", price = 280},
        {item_id = "02020005", price = 332},
        {item_id = "02001002", price = 4160},
        {item_id = "02001001", price = 2392},
        {item_id = "02001000", price = 3328},
        {item_id = "02002005", price = 520},
        {item_id = "02002004", price = 520},
        {item_id = "02002002", price = 520},
        {item_id = "02002001", price = 416},
        {item_id = "02002000", price = 520},
        {item_id = "02000006", price = 385},
        {item_id = "02000003", price = 150},
        {item_id = "02000002", price = 332},
        {item_id = "02000001", price = 150},
      }
    },
  }
end

return M
