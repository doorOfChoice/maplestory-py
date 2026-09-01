"""吸附中的掉落物应快速到达玩家（原版：捡起一件、同层附近全吸）。"""

from types import SimpleNamespace

from game.systems.combat import Combat, DropItem


def test_attracted_drop_reaches_player_fast():
    c = Combat(None)
    d = DropItem(200.0, -4.0, meso=5, ground_y=0.0)
    d.vy = 0.0
    d.vx = 0.0
    d.attracted = True
    c.drops.append(d)
    player = SimpleNamespace(x=0.0, y=-20.0)
    picked = False
    for _ in range(45):       # 0.75s 内应到位（吸附物由 update 自动收取）
        if c.update(1 / 60, player):
            picked = True
            break
    assert picked
