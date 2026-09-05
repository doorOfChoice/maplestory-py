-- 2020001（斯考特）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "2020001_shop_1",
      name = "商店",
      items = {
        {item_id = "01492006", price = 160000},
        {item_id = "01492005", price = 100000},
        {item_id = "01482006", price = 150000},
        {item_id = "01482005", price = 100000},
        {item_id = "01472007", price = 60000},
        {item_id = "01472004", price = 30000},
        {item_id = "01462005", price = 250000},
        {item_id = "01462004", price = 200000},
        {item_id = "01452007", price = 375000},
        {item_id = "01452006", price = 250000},
        {item_id = "01442009", price = 300000},
        {item_id = "01442003", price = 175000},
        {item_id = "01432005", price = 225000},
        {item_id = "01432003", price = 175000},
        {item_id = "01422007", price = 250000},
        {item_id = "01422008", price = 200000},
        {item_id = "01412005", price = 250000},
        {item_id = "01412004", price = 200000},
        {item_id = "01402007", price = 450000},
        {item_id = "01402006", price = 350000},
        {item_id = "01372000", price = 400000},
        {item_id = "01372001", price = 175000},
        {item_id = "01332011", price = 425000},
        {item_id = "01332014", price = 375000},
        {item_id = "01332001", price = 200000},
        {item_id = "01322016", price = 175000},
        {item_id = "01322015", price = 100000},
        {item_id = "01312007", price = 175000},
        {item_id = "01312006", price = 100000},
        {item_id = "01302009", price = 225000},
        {item_id = "01302004", price = 100000},
      }
    },
  }
end

return M
