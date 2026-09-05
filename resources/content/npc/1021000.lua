-- 1021000（利伯）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1021000_shop_1",
      name = "商店",
      items = {
        {item_id = "01442004", price = 24000},
        {item_id = "01442007", price = 12000},
        {item_id = "01442006", price = 8000},
        {item_id = "01442000", price = 3000},
        {item_id = "01432001", price = 7000},
        {item_id = "01432000", price = 3000},
        {item_id = "01422004", price = 20000},
        {item_id = "01422006", price = 10000},
        {item_id = "01422003", price = 10000},
        {item_id = "01422002", price = 6000},
        {item_id = "01422000", price = 3000},
        {item_id = "01412006", price = 45000},
        {item_id = "01412000", price = 22000},
        {item_id = "01412002", price = 10000},
        {item_id = "01412001", price = 3000},
        {item_id = "01402008", price = 22000},
        {item_id = "01402000", price = 12000},
        {item_id = "01402001", price = 3000},
        {item_id = "01322014", price = 40000},
        {item_id = "01322004", price = 22000},
        {item_id = "01322002", price = 10000},
        {item_id = "01322000", price = 6000},
        {item_id = "01312005", price = 40000},
        {item_id = "01312003", price = 20000},
        {item_id = "01312001", price = 6000},
        {item_id = "01332010", price = 22000},
        {item_id = "01332008", price = 10000},
        {item_id = "01332006", price = 7000},
        {item_id = "01302008", price = 40000},
        {item_id = "01302003", price = 20000},
        {item_id = "01302006", price = 10000},
        {item_id = "01302002", price = 10000},
        {item_id = "01302005", price = 6000},
        {item_id = "01302007", price = 3000},
      }
    },
  }
end

return M
