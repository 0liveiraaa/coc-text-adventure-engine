import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest

from src.data.init.world_loader import load_initial_world_bundle
from src.engine.game_engine import GameEngine


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


class PriorityTests(unittest.TestCase):
    def test_filters_out_hp_or_san_zero(self):
        bundle = load_initial_world_bundle(_FakeIO(), player_name="测试者", world_name="mysterious_library")
        engine = GameEngine(io_system=_FakeIO())
        engine.game_state = bundle.game_state

        player = engine.game_state.get_player()
        guard = engine.game_state.characters.get("char-guard-01")
        self.assertIsNotNone(player)
        self.assertIsNotNone(guard)

        guard.status.hp = 0
        queue = engine._build_dynamic_action_queue()

        self.assertNotIn("char-guard-01", queue)
        self.assertIn(player.id, queue)

    def test_priority_order_is_dex_then_hp_ratio_then_san_ratio_then_id(self):
        bundle = load_initial_world_bundle(_FakeIO(), player_name="测试者", world_name="mysterious_library")
        engine = GameEngine(io_system=_FakeIO())
        engine.game_state = bundle.game_state

        player = engine.game_state.characters["char-player-01"]
        guard = engine.game_state.characters["char-guard-01"]

        player.attributes.dex = 70
        guard.attributes.dex = 70

        player.status.max_hp = 10
        player.status.hp = 8
        guard.status.max_hp = 10
        guard.status.hp = 8

        player.status.san = 60
        guard.status.san = 60

        queue = engine._build_dynamic_action_queue()

        self.assertEqual(queue[0], min(["char-player-01", "char-guard-01"]))


if __name__ == "__main__":
    unittest.main()
