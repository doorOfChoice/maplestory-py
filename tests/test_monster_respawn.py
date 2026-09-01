"""怪物重生调度：死亡移除后排队，到期回传出生数据重建。"""

from game.monster import RespawnQueue


def test_respawn_fires_only_after_delay():
    q = RespawnQueue(5.0)
    q.schedule(3, {"id": "0100101", "x": 100})
    assert q.tick(4.0) == []
    assert q.tick(1.5) == [(3, {"id": "0100101", "x": 100})]
    assert q.tick(1.0) == []


def test_respawn_queue_handles_multiple_entries():
    q = RespawnQueue(2.0)
    q.schedule(0, {"id": "a"})
    q.tick(1.0)
    q.schedule(1, {"id": "b"})
    out = q.tick(1.5)
    assert (0, {"id": "a"}) in out
    assert (1, {"id": "b"}) not in out
    assert (1, {"id": "b"}) in q.tick(1.0)


def test_respawn_clear_drops_pending():
    q = RespawnQueue(5.0)
    q.schedule(0, {"id": "a"})
    q.clear()
    assert q.tick(10.0) == []
