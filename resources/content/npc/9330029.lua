-- 9330029（阿凤）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9330029_shop_1",
      name = "商店",
      items = {
        {item_id = "02000001", price = 150},
        {item_id = "02000002", price = 280},
        {item_id = "02000003", price = 150},
        {item_id = "02000006", price = 180},
        {item_id = "02010004", price = 180},
        {item_id = "02020000", price = 420},
        {item_id = "02020001", price = 206},
        {item_id = "02020005", price = 332},
        {item_id = "02020003", price = 427},
        {item_id = "02020007", price = 1200},
        {item_id = "02001000", price = 3328},
        {item_id = "02020008", price = 2000},
        {item_id = "02001001", price = 2185},
        {item_id = "02001002", price = 4000},
        {item_id = "02022021", price = 2300},
        {item_id = "02022022", price = 2600},
        {item_id = "02022017", price = 1100},
        {item_id = "02022018", price = 1600},
        {item_id = "02022020", price = 550},
        {item_id = "02022014", price = 650},
      }
    },
  }
end

return M
