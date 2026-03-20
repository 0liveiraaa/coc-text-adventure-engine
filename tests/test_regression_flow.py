import unittest

from src.data.io_system import ERROR_SUCCESS
from src.data.init.world_loader import load_initial_world_bundle
from src.data.models import DMAgentOutput, StateEvolutionOutput, GameState
from src.engine.game_engine import GameEngine


class FakeIO:
    """最小IO桩，避免测试依赖数据库驱动。"""

    def save_character(self, _):
        return ERROR_SUCCESS

    def save_item(self, _):
        return ERROR_SUCCESS

    def save_map(self, _):
        return ERROR_SUCCESS

    def clear_current_events(self):
        return ERROR_SUCCESS

    def apply_state_change(self, _):
        return ERROR_SUCCESS


class DummyDMAgent:
    def parse_intent(self, player_input: str, game_state: GameState):
        return DMAgentOutput(
            is_dialogue=False,
            response_to_player="",
            needs_check=False,
            check_type=None,
            check_attributes=[],
            check_target=None,
            difficulty="常规",
            action_description=player_input,
        )


class DummyStateAgent:
    def __init__(self):
        self.end_condition = ""

    def evolve_player_action(self, check_result, action_description, game_state, additional_context=None):
        return StateEvolutionOutput(
            narrative="你调整了呼吸，短暂观察四周。",
            changes=[],
            resolved=True,
            next_action_hint=None,
            is_end=False,
            end_narrative="",
        )


class RegressionFlowTests(unittest.TestCase):
    def test_world_bundle_loader_with_split_files(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        self.assertEqual(bundle.world_name, "mysterious_library")
        self.assertTrue(bundle.end_condition)
        self.assertIn("char-player-01", bundle.game_state.characters)
        self.assertIn("map-room-library-01", bundle.game_state.maps)

    def test_config_ending_is_evaluated(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=DummyStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        # 强制触发 death ending
        player = engine.game_state.get_player()
        self.assertIsNotNone(player)
        player.status.hp = 0

        result = engine.process_input("我什么也不做")
        self.assertTrue(result["game_over"])
        self.assertIn("图书馆重新归于沉寂", result.get("narrative") or "")


if __name__ == "__main__":
    unittest.main()
