-- 转职会话：宿主把本模块当作一场转职对话的状态机。
-- 宿主契约：
--   ctx = { player={level,job}, jobdef={code,name,advance_lv}, npc_name }
--   全局：can_advance() -> bool（读 ctx 判定）；advance_job()（改真身并置 ctx.advanced）
--   会话：new(ctx)；snapshot() -> {npc,lines,mode,options}；choose(label)；done
local M = {}

function M.new(ctx)
	local self = setmetatable({}, { __index = M })
	self.ctx, self.done = ctx, false
	if ctx.player.job == ctx.jobdef.code then
		self.state = "already"
	elseif can_advance() then
		self.state = "confirm"
	else
		self.state = "weak"
	end
	return self
end

function M:snapshot()
	local c = self.ctx
	if self.state == "already" then
		return { npc = c.npc_name,
			lines = { "你已经是一名出色的" .. c.jobdef.name .. "了。" }, mode = "quest" }
	elseif self.state == "weak" then
		return { npc = c.npc_name,
			lines = { "你还太弱小了，达到等级再来找我吧。",
				string.format("（当前 Lv%d / 需要 Lv%d）", c.player.level, c.jobdef.advance_lv) },
			mode = "quest" }
	elseif self.state == "confirm" then
		return { npc = c.npc_name,
			lines = { "你想成为" .. c.jobdef.name .. "吗？",
				"达到 Lv" .. c.jobdef.advance_lv .. " 就可以转职为" .. c.jobdef.name .. "，",
				"转职后我会教你该职业的技能。" },
			mode = "quest", options = { "yes", "no" } }
	elseif self.state == "declined" then
		return { npc = c.npc_name,
			lines = { "好吧，改变心意的话再来找我。" }, mode = "quest", options = { "ok" } }
	end
	return { npc = c.npc_name,
		lines = { "恭喜！你已转职为", "" .. c.jobdef.name .. "了！" },
		mode = "quest", options = { "ok" } }
end

function M:choose(label)
	if self.state == "confirm" and label == "yes" then
		advance_job()
		self.state = "advanced"
		return
	elseif self.state == "confirm" and label == "no" then
		self.state = "declined"
		return
	end
	self.done = true
end

return M
