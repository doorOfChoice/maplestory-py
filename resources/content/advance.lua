-- 转职对话：talk(ctx) 步骤图。宿主契约见 resources/content/AGENTS.md。
local M = {}

function M.talk(ctx)
	local jd = ctx.jobdef
	local name = ctx.npc.name
	if ctx.player.job == jd.code then
		return { title = name, start = "already", steps = {
			already = { text = { "你已经是一名出色的" .. jd.name .. "了。" } } } }
	end
	if can_advance() then
		return { title = name, start = "confirm", steps = {
			confirm = {
				text = { "你想成为" .. jd.name .. "吗？",
					"达到 Lv" .. jd.advance_lv .. " 就可以转职为" .. jd.name .. "，",
					"转职后我会教你该职业的技能。" },
				buttons = { yes = function(c) advance_job() return "advanced" end,
					no = "declined" } },
			advanced = { text = { "恭喜！你已转职为", "" .. jd.name .. "了！" } },
			declined = { text = { "好吧，改变心意的话再来找我。" } } } }
	end
	return { title = name, start = "weak", steps = {
		weak = { text = { "你还太弱小了，达到等级再来找我吧。",
			string.format("（当前 Lv%d / 需要 Lv%d）",
				ctx.player.level, jd.advance_lv) } } } }
end

return M
