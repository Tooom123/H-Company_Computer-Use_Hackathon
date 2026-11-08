import random

from hcs_agent.overlay_layout import tape_slots


def test_tape_count_and_gravity():
    counts = set()
    for seed in range(500):
        slots = tape_slots(random.Random(seed))
        counts.add(len(slots))
        assert 2 <= len(slots) <= 4
        assert len(set(slots)) == len(slots)
        assert any(s.startswith("top") for s in slots), slots  # never only at the bottom
        assert any(s.endswith("left") for s in slots) and any(s.endswith("right") for s in slots), slots
    assert counts == {2, 3, 4}


def test_tape_is_stable_for_a_seed():
    assert tape_slots(random.Random(11)) == tape_slots(random.Random(11))
