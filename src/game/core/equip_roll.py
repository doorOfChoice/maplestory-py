"""掉落的装备基础属性浮动：纯函数 roll_drop_bonus，注入 rng 可测。

不依赖 pygame / WZ。掉落加成直接落在主属性池（力量/敏捷/智力/运气/
最大HP/最大MP/攻击力/魔法力），数值 +1~+5，由调用方写进 Item.info（非
extra），实现「同一装备每次掉落基础值不同」。卷轴强化仍走 extra，两者互不
干扰：tooltip 里绿色 (+N) 只表示卷轴加的，掉落浮动则是平淡的基础值。
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from game import settings

# rng 契约：random 协议 —— random() 判掉率、sample(pool, n) 挑词条、
# randint(lo, hi) 给每条数值；可用 random.Random(seed) 或自定义实现。


def roll_drop_bonus(rng,
                    *,
                    chance: float = settings.DROP_RARE_CHANCE,
                    line_range: Sequence[int] = settings.DROP_RARE_LINES,
                    bonus_range: Sequence[int] = settings.DROP_RARE_BONUS,
                    pool: Sequence[str] = settings.DROP_RARE_STATS
                    ) -> dict:
    """掷一件「稀有」装备的随机浮动：未命中掉率返回空；命中则挑 2~4 条主属性。

    返回值是 {词条键: 浮动值}，调用方负责并入 Item.info。同种子确定性。
    """
    if rng.random() >= chance:
        return {}
    keys = rng.sample(list(pool), rng.randint(line_range[0], line_range[1]))
    bonus: dict = {}
    for key in keys:
        bonus[key] = rng.randint(bonus_range[0], bonus_range[1])
    return bonus
