-- 发奖能力测试脚本（仅供 test_lua_reward.py，不入游戏流程）
local M = {}
local last = "nil"

function M.talk(ctx)
	local function branch(f)
		return function(c) last = tostring(f()) return "result" end
	end
	return { start = "pick", steps = {
		pick = { text = { "choose" }, links = {
			{ label = "full",      click = branch(function() return give_reward(500, 1000, { { 2000000, 3 } }) end) },
			{ label = "exp_only",  click = branch(function() return give_reward(500) end) },
			{ label = "empty",     click = branch(function() return give_reward() end) },
			{ label = "negative",  click = branch(function() return give_reward(0, 0, { { 2000000, -1 } }) end) },
		} },
		result = { text = function(c) return { "result:" .. last } end } } }
end

return M
