-- 1001001（娜塔莎）：官方 v113 商店货架（自动生成，勿手改）
-- 数据源：src/scripts/data/official_shops.csv（重跑 import_official_shops.py 再生成）
local M = {}

function M.shops()
  return {
    {
      shop_id = "1001001_shop_1",
      name = "商店",
      items = {
        {item_id = "03010001", price = 1000},
        {item_id = "01092003", price = 2000},
        {item_id = "01072063", price = 10000},
        {item_id = "01072062", price = 10000},
        {item_id = "01072017", price = 10000},
        {item_id = "01072049", price = 5000},
        {item_id = "01072048", price = 5000},
        {item_id = "01072008", price = 5000},
        {item_id = "01072005", price = 50},
        {item_id = "01072038", price = 50},
        {item_id = "01072037", price = 50},
        {item_id = "01072001", price = 50},
        {item_id = "01062001", price = 4800},
        {item_id = "01062000", price = 4800},
        {item_id = "01060004", price = 2800},
        {item_id = "01060007", price = 1000},
        {item_id = "01041012", price = 3000},
        {item_id = "01041004", price = 3000},
        {item_id = "01040014", price = 3000},
        {item_id = "01040013", price = 3000},
        {item_id = "01002001", price = 3000},
        {item_id = "01002019", price = 2000},
        {item_id = "01002134", price = 800},
        {item_id = "01002133", price = 800},
        {item_id = "01002132", price = 800},
        {item_id = "01002069", price = 450},
        {item_id = "01002068", price = 450},
        {item_id = "01002067", price = 450},
        {item_id = "01002066", price = 450},
        {item_id = "01002014", price = 1000},
        {item_id = "01002008", price = 500},
      }
    },
  }
end

return M
