import unittest

from src.narrative import NarrativeContext, NarrativeContextSnapshot, NarrativeEvent


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

    def test_llm_context_is_bounded(self):
        ctx = NarrativeContext(window_size=1, max_summary_lines=2, max_context_chars=180)
        for turn in range(1, 8):
            ctx.add_event(
                NarrativeEvent(
                    turn=turn,
                    actor_id="player",
                    text=("Very long narrative segment " * 8) + str(turn),
                )
            )

        context_text = ctx.get_context_for_llm()
        self.assertLessEqual(len(context_text), 180)
        self.assertLessEqual(len(ctx.summary_lines), 2)

    def test_from_snapshot_preserves_summary_lines_and_key_facts(self):
        snapshot = NarrativeContextSnapshot(
            window_size=2,
            recent_events=[
                NarrativeEvent(
                    turn=10,
                    actor_id="char-guard-01",
                    actor_name="Guard",
                    text="Guard points at map-room-secret-01",
                    source="npc_reactive",
                    key_facts=["map-room-secret-01"],
                )
            ],
            summary_lines=["[Turn 1] player: Found item-key-01"],
            key_facts=["item-key-01"],
        )

        rebuilt = NarrativeContext.from_snapshot(snapshot)

        self.assertIn("item-key-01", rebuilt.key_facts)
        self.assertIn("map-room-secret-01", rebuilt.key_facts)
        self.assertIn("[Turn 1] player: Found item-key-01", rebuilt.summary)


if __name__ == "__main__":
    unittest.main()

