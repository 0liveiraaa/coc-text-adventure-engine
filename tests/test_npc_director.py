import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from src.data.init.world_loader import load_initial_world_bundle
from src.data.models import DMAgentOutput, StateEvolutionOutput
from src.engine.game_engine import GameEngine


class FakeIO:
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


class ReactiveWithoutIntentDMAgent:
    def parse_intent(self, player_input, game_state, additional_context=None):
        return DMAgentOutput(
            is_dialogue=False,
            response_to_player="",
            needs_check=False,
            check_type=None,
            check_attributes=[],
            check_target=None,
            difficulty="常规",
            action_description=player_input,
            npc_response_needed=True,
            npc_actor_id="char-guard-01",
            npc_intent=None,
        )


class DirectorAwareStateAgent:
    def __init__(self):
        self.end_condition = ""
        self.last_npc_intent = None
        self.last_npc_context = None

    def evolve_player_action(self, check_result, action_description, game_state, additional_context=None):
        return StateEvolutionOutput(
            narrative="你停在原地观察守卫。",
            changes=[],
            resolved=True,
            next_action_hint=None,
            is_end=False,
            end_narrative="",
        )

    def evolve_npc_action(self, npc_id, game_state, check_result=None, npc_intent=None, additional_context=None):
        self.last_npc_intent = npc_intent
        self.last_npc_context = additional_context or {}
        return StateEvolutionOutput(
            narrative="守卫做出了回应。",
            changes=[],
            resolved=True,
            next_action_hint=None,
            is_end=False,
            end_narrative="",
        )

    def check_end_condition(self, game_state):
        return None


class NPCDirectorIntegrationTests(unittest.TestCase):
    def test_queue_mode_plans_action_through_director(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")
        engine = GameEngine(io_system=FakeIO())
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        plans = engine._plan_npc_actions(trigger="queue", candidate_npc_ids=["char-guard-01"])

        self.assertIn("char-guard-01", plans)
        self.assertEqual(plans["char-guard-01"].get("trigger_source"), "queue")

    def test_reactive_mode_uses_structured_plan_intent(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = DirectorAwareStateAgent()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=ReactiveWithoutIntentDMAgent(),
            state_agent=state_agent,
            npc_response_mode="reactive",
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("我靠近守卫")

        self.assertTrue(result["success"])
        self.assertIn("守卫做出了回应", result.get("narrative") or "")
        self.assertEqual(state_agent.last_npc_intent, "对玩家刚刚的行动做出回应")
        self.assertEqual(state_agent.last_npc_context.get("trigger"), "reactive")


if __name__ == "__main__":
    unittest.main()
