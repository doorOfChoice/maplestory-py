-- 2041006（米斯级）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "2041006_shop_1",
      name = "商店",
      items = {
        {item_id = "02061001", price = 10},
        {item_id = "02060001", price = 10},
        {item_id = "02061000", price = 1},
        {item_id = "02060000", price = 1},
        {item_id = "02030000", price = 400},
        {item_id = "02020028", price = 2850},
        {item_id = "02020006", price = 503},
        {item_id = "02020005", price = 304},
        {item_id = "02020004", price = 427},
        {item_id = "02020003", price = 427},
        {item_id = "02020002", price = 304},
        {item_id = "02020001", price = 209},
        {item_id = "02010002", price = 47},
        {item_id = "02010001", price = 106},
        {item_id = "02002010", price = 500},
        {item_id = "02002009", price = 500},
        {item_id = "02002008", price = 500},
        {item_id = "02002007", price = 500},
        {item_id = "02002006", price = 500},
        {item_id = "02001002", price = 3800},
        {item_id = "02001001", price = 2185},
        {item_id = "02000006", price = 589},
        {item_id = "02000011", price = 620},
        {item_id = "02000003", price = 190},
        {item_id = "02000010", price = 200},
        {item_id = "02000002", price = 304},
        {item_id = "02000009", price = 320},
        {item_id = "02000001", price = 152},
        {item_id = "02000008", price = 160},
        {item_id = "02000000", price = 47},
        {item_id = "02000007", price = 50},
        {item_id = "02330000", price = 600},
        {item_id = "02070000", price = 500},
      }
    },
  }
end

return M
