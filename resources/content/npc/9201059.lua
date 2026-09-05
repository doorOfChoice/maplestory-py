-- 9201059（凯尔）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "9201059_shop_1",
      name = "商店",
      items = {
        {item_id = "01472001", price = 22500},
        {item_id = "01462000", price = 32500},
        {item_id = "01452005", price = 152500},
        {item_id = "01442001", price = 62500},
        {item_id = "01432002", price = 62500},
        {item_id = "01422001", price = 47500},
        {item_id = "01412006", price = 47500},
        {item_id = "01402002", price = 152500},
        {item_id = "01382002", price = 22500},
        {item_id = "01372003", price = 40500},
        {item_id = "01332012", price = 42500},
        {item_id = "01332009", price = 44500},
        {item_id = "01322014", price = 42500},
        {item_id = "01312005", price = 42500},
        {item_id = "01302068", price = 352500},
      }
    },
  }
end

return M
