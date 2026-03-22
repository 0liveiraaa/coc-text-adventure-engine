import unittest

from src.data.npc_planning_models import (
    NPCActionDecision,
    NPCActionForm,
    NPCActionType,
    NPCCheckDifficulty,
)


class TestNPCPlanningModels(unittest.TestCase):
    def test_action_form_defaults(self):
        action = NPCActionForm(npc_id="char-npc-01")
        self.assertEqual(action.action_type, NPCActionType.WAIT)
        self.assertFalse(action.check.check_needed)
        self.assertEqual(action.check.difficulty, NPCCheckDifficulty.REGULAR)

    def test_action_decision_batch(self):
        action = NPCActionForm(
            npc_id="char-npc-02",
            action_type=NPCActionType.TALK,
            target_id="char-player-01",
            intent_description="Ask the player to leave the room",
        )
        decision = NPCActionDecision(actions={action.npc_id: action}, rationale="Guard behavior")
        self.assertIn("char-npc-02", decision.actions)
        self.assertEqual(decision.actions["char-npc-02"].action_type, NPCActionType.TALK)


if __name__ == "__main__":
    unittest.main()

