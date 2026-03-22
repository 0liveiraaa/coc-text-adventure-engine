import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from src.data.npc_planning_models import NPCActionForm, NPCActionType
from src.data.init.world_loader import load_initial_world_bundle
from src.engine.game_engine import GameEngine
from src.narrative import NarrativeContext, NarrativeContextSnapshot, NarrativeEvent


class _FakeIO:
    def save_character(self, _):
        return 0

    def save_item(self, _):
        return 0

    def save_map(self, _):
        return 0

    def clear_current_events(self):
        return 0

    def apply_state_change(self, _):
        return 0


class ArchitectureRefactorIncrementTests(unittest.TestCase):
    def test_narrative_context_export_contains_recent_events_and_summary(self):
        context = NarrativeContext(window_size=2)
        context.add_event(NarrativeEvent(turn=1, actor_id="player", text="Open the old door"))
        context.add_event(NarrativeEvent(turn=2, actor_id="guard", text="The guard warns you"))
        context.add_event(NarrativeEvent(turn=3, actor_id="player", text="Search for a clue"))

        exported = context.export_state()

        self.assertEqual(len(exported["recent_events"]), 2)
        self.assertIn("summary", exported)
        self.assertIn("key_facts", exported)

    def test_narrative_snapshot_round_trip_preserves_key_facts(self):
        snapshot = NarrativeContextSnapshot(
            window_size=3,
            recent_events=[
                NarrativeEvent(
                    turn=4,
                    actor_id="npc-1",
                    text="NPC loses SAN and sees blood",
                    key_facts=["san_drop:npc-1:1", "blood_seen"],
                )
            ],
            summary_lines=["[Turn 1] player: Found a clue"],
            key_facts=["san_drop:npc-1:1", "blood_seen"],
        )

        rebuilt = NarrativeContext.from_snapshot(snapshot)

        self.assertEqual(rebuilt.window_size, 3)
        self.assertIn("san_drop:npc-1:1", rebuilt.key_facts)
        self.assertIn("blood_seen", rebuilt.key_facts)

    def test_structured_npc_action_form_uses_nested_check_plan(self):
        action = NPCActionForm(
            npc_id="char-guard-01",
            action_type=NPCActionType.TALK,
            target_id="char-player-01",
            intent_description="Warn the player to be quiet",
        )

        dumped = action.model_dump()

        self.assertEqual(dumped["npc_id"], "char-guard-01")
        self.assertEqual(dumped["action_type"], "talk")
        self.assertIn("check", dumped)
        self.assertFalse(dumped["check"]["check_needed"])

    def test_world_bundle_exposes_narrative_window(self):
        bundle = load_initial_world_bundle(_FakeIO(), player_name="测试者", world_name="mysterious_library")
        self.assertGreaterEqual(bundle.narrative_window, 1)

    def test_engine_restore_narrative_context_keeps_summary_and_facts(self):
        engine = GameEngine(io_system=_FakeIO())

        payload = {
            "window_size": 2,
            "recent_events": [
                {
                    "turn": 3,
                    "actor_id": "char-guard-01",
                    "actor_name": "Guard",
                    "text": "Guard reveals a clue about item-key-01",
                    "source": "npc_queue",
                    "key_facts": ["item-key-01"],
                }
            ],
            "summary_lines": ["[Turn 1] player: Moved to map-room-secret-01"],
            "key_facts": ["map-room-secret-01"],
        }
        engine._restore_narrative_context(payload)

        exported = engine._dump_narrative_context()
        self.assertEqual(exported.get("window_size"), 2)
        self.assertIn("map-room-secret-01", exported.get("key_facts", []))
        self.assertIn("item-key-01", exported.get("key_facts", []))
        self.assertTrue(exported.get("summary_lines"))


if __name__ == "__main__":
    unittest.main()
