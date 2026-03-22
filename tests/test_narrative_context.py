import unittest

from src.narrative import NarrativeContext, NarrativeEvent


class TestNarrativeContext(unittest.TestCase):
    def test_window_and_compression(self):
        ctx = NarrativeContext(window_size=2)

        ctx.add_event(NarrativeEvent(turn=1, actor_id="player", text="Open the old door"))
        ctx.add_event(NarrativeEvent(turn=2, actor_id="npc-1", text="Guard shouts loudly"))
        ctx.add_event(NarrativeEvent(turn=3, actor_id="player", text="Run into hallway"))

        self.assertEqual(len(ctx.recent_events), 2)
        self.assertEqual(len(ctx.summary_lines), 1)
        self.assertIn("player", ctx.summary_lines[0])

    def test_snapshot_round_trip(self):
        ctx = NarrativeContext(window_size=2)
        ctx.add_event(
            NarrativeEvent(
                turn=7,
                actor_id="npc-2",
                text="NPC uses lantern and loses SAN by 1",
                key_facts=["san_drop:npc-2:1"],
            )
        )

        snapshot = ctx.to_snapshot()
        rebuilt = NarrativeContext.from_snapshot(snapshot)

        self.assertEqual(rebuilt.window_size, 2)
        self.assertEqual(len(rebuilt.recent_events), 1)
        self.assertIn("san_drop:npc-2:1", rebuilt.key_facts)


if __name__ == "__main__":
    unittest.main()

