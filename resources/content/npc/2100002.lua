-- 2100002（渣伊德）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "2100002_shop_1",
      name = "商店",
      items = {
        {item_id = "01492004", price = 75000},
        {item_id = "01482004", price = 75000},
        {item_id = "01472001", price = 20000},
        {item_id = "01462000", price = 30000},
        {item_id = "01452005", price = 150000},
        {item_id = "01442001", price = 60000},
        {item_id = "01432002", price = 60000},
        {item_id = "01422001", price = 45000},
        {item_id = "01412006", price = 45000},
        {item_id = "01402002", price = 150000},
        {item_id = "01382002", price = 20000},
        {item_id = "01372003", price = 38000},
        {item_id = "01332012", price = 40000},
        {item_id = "01332009", price = 42000},
        {item_id = "01322014", price = 40000},
        {item_id = "01312005", price = 40000},
        {item_id = "01302008", price = 40000},
      }
    },
  }
end

return M
