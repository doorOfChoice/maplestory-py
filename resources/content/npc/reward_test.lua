-- 发奖能力测试脚本：宿主注入 give_reward，验证不同参数组合的发放与返回值。
-- 仅供单测使用（test_lua_reward.py），不入游戏流程。
local M = {}

function M.new(ctx)
	local self = setmetatable({}, { __index = M })
	self.ctx, self.done = ctx, false
	self.state = "pick"
	self.result = nil
	return self
end

function M:snapshot()
	if self.state == "pick" then
		return { npc = self.ctx.npc_name, lines = { "choose" },
			mode = "quest", options = { "full", "exp_only", "empty", "negative" } }
	end
	return { npc = self.ctx.npc_name,
		lines = { "result:" .. tostring(self.result) },
		mode = "quest", options = { "ok" } }
end

function M:choose(label)
	if self.state == "pick" then
		if label == "full" then
			self.result = give_reward(500, 1000, { { 2000000, 3 } })
		elseif label == "exp_only" then
			self.result = give_reward(500, nil, nil)
		elseif label == "empty" then
			self.result = give_reward()
		elseif label == "negative" then
			self.result = give_reward(0, 0, { { 2000000, -1 } })
		end
		self.state = "done"
		return
	end
	self.done = true
end

return M
