import unittest

from src.data.models import ChangeOperation, DMAgentOutput, Memory, StateChange
from src.data.npc_planning_models import NPCActionForm, NPCActionType
from src.narrative import NarrativeContext, NarrativeEvent


class ArchitectureRefactorTests(unittest.TestCase):
    def test_memory_tracks_event_history(self):
        memory = Memory()
        memory.current_event = "first beat"
        memory.push_to_log("second beat")
        self.assertEqual(memory.log, ["first beat"])
        self.assertEqual(memory.current_event, "second beat")
        memory.clear_current()
        self.assertEqual(memory.log, ["first beat", "second beat"])
        self.assertEqual(memory.current_event, "")

    def test_dmagnet_output_serialization_retains_npc_fields(self):
        agent_output = DMAgentOutput(
            is_dialogue=False,
            response_to_player="ok",
            needs_check=True,
            check_type="Regular",
            check_attributes=["int"],
            check_target="char-guard-01",
            difficulty="Regular",
            action_description="ask politely",
            npc_response_needed=True,
            npc_actor_id="char-guard-01",
            npc_intent="inspect the corridor",
        )
        data = agent_output.model_dump()
        self.assertTrue(data["npc_response_needed"])
        self.assertEqual(data["npc_actor_id"], "char-guard-01")
        self.assertEqual(data["npc_intent"], "inspect the corridor")
        serialized = agent_output.model_dump_json()
        self.assertIn("npc_response_needed", serialized)
        self.assertIn("inspect the corridor", serialized)

    def test_state_change_serialization_roundtrip(self):
        change = StateChange(
            id="char-player-01",
            field="status.hp",
            operation=ChangeOperation.UPDATE,
            value=5,
        )
        data = change.model_dump()
        self.assertEqual(data["value"], 5)
        serialized = change.model_dump_json()
        self.assertIn('"value":5', serialized)

    def test_narrative_context_smoke(self):
        context = NarrativeContext(window_size=2)
        context.add_event(NarrativeEvent(turn=1, actor_id="player", text="Open the old door"))
        context.add_event(NarrativeEvent(turn=2, actor_id="guard", text="The guard warns you"))
        context.add_event(NarrativeEvent(turn=3, actor_id="player", text="Search for a clue"))
        exported = context.export_state()

        self.assertEqual(len(exported["recent_events"]), 2)
        self.assertIn("summary", exported)
        self.assertIn("key_facts", exported)

    def test_npc_action_form_defaults(self):
        action = NPCActionForm(npc_id="char-npc-01")
        self.assertEqual(action.action_type, NPCActionType.WAIT)
        self.assertFalse(action.check.check_needed)


if __name__ == "__main__":
    unittest.main()
