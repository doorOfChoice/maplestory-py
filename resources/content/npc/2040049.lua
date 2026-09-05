-- 2040049（糖果机）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "2040049_shop_1",
      name = "商店",
      items = {
        {item_id = "02061001", price = 10},
        {item_id = "02060001", price = 10},
        {item_id = "02061000", price = 1},
        {item_id = "02060000", price = 1},
        {item_id = "02120000", price = 30},
        {item_id = "02020015", price = 10608},
        {item_id = "02020014", price = 8424},
        {item_id = "02020013", price = 5824},
        {item_id = "02020012", price = 4680},
        {item_id = "02022000", price = 1155},
        {item_id = "02022003", price = 1144},
        {item_id = "02020006", price = 503},
        {item_id = "02020005", price = 304},
        {item_id = "02020004", price = 427},
        {item_id = "02020003", price = 427},
        {item_id = "02020002", price = 304},
        {item_id = "02020001", price = 209},
        {item_id = "02010002", price = 50},
        {item_id = "02010001", price = 150},
        {item_id = "02002010", price = 475},
        {item_id = "02002009", price = 570},
        {item_id = "02002008", price = 570},
        {item_id = "02002007", price = 570},
        {item_id = "02002006", price = 570},
        {item_id = "02001002", price = 4000},
        {item_id = "02001001", price = 2300},
        {item_id = "02000006", price = 385},
        {item_id = "02000011", price = 385},
        {item_id = "02000003", price = 150},
        {item_id = "02000010", price = 150},
        {item_id = "02000002", price = 280},
        {item_id = "02000009", price = 280},
        {item_id = "02000001", price = 150},
        {item_id = "02000008", price = 150},
        {item_id = "02000000", price = 30},
        {item_id = "02000007", price = 50},
      }
    },
  }
end

return M
