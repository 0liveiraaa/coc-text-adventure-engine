import unittest
import tempfile

from src.data.io_system import ERROR_SUCCESS, ERROR_ID_NOT_FOUND, IOSystem
from src.data.init.world_loader import load_initial_world_bundle
from src.data.models import (
    DMAgentOutput,
    StateEvolutionOutput,
    GameState,
    StateChange,
    ChangeOperation,
    Character,
    Item,
)
from src.agent.input_system import InputSystem, InputType
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


class DummyRuleSystem:
    def __init__(self):
        self.calls = 0

    def execute_check(self, check_input, game_state):
        self.calls += 1
        from src.data.models import CheckOutput, CheckResult
        return CheckOutput(
            result=CheckResult.SUCCESS,
            dice_roll=30,
            target_value=50,
            actor_value=50,
            detail="NPC检定成功",
        )


class DummyDMAgent:
    def parse_intent(self, player_input: str, game_state: GameState, additional_context=None):
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

    def check_end_condition(self, game_state):
        return None


class AliasIdStateAgent:
    def __init__(self):
        self.end_condition = ""

    def evolve_player_action(self, check_result, action_description, game_state, additional_context=None):
        return StateEvolutionOutput(
            narrative="你拿起了煤油灯。",
            changes=[
                StateChange(
                    id="player_001",
                    field="inventory",
                    operation=ChangeOperation.UPDATE,
                    value=["item-lantern-01"],
                )
            ],
            resolved=True,
            next_action_hint=None,
            is_end=False,
            end_narrative="",
        )

    def check_end_condition(self, game_state):
        return None


class AiEndReviewStateAgent(DummyStateAgent):
    def check_end_condition(self, game_state):
        return StateEvolutionOutput(
            narrative="",
            changes=[],
            resolved=True,
            next_action_hint=None,
            is_end=True,
            end_narrative="你的视野被无尽黑暗吞没，故事到此结束。",
        )


class NpcCapableStateAgent(DummyStateAgent):
    def __init__(self):
        super().__init__()
        self.npc_calls = 0

    def evolve_npc_action(self, npc_id, game_state, check_result=None, npc_intent=None, additional_context=None):
        self.npc_calls += 1
        self.last_check_result = check_result
        return StateEvolutionOutput(
            narrative="守卫低声提醒你保持安静。",
            changes=[
                StateChange(
                    id="char-player-01",
                    field="status.san",
                    operation=ChangeOperation.UPDATE,
                    value=59,
                )
            ],
            resolved=True,
            next_action_hint=None,
            is_end=False,
            end_narrative="",
        )


class ReactiveDMAgent(DummyDMAgent):
    def parse_intent(self, player_input: str, game_state: GameState, additional_context=None):
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
            npc_intent="对玩家刚才的行动做出警告",
        )


class ReactiveNoNpcDMAgent(DummyDMAgent):
    def parse_intent(self, player_input: str, game_state: GameState, additional_context=None):
        return DMAgentOutput(
            is_dialogue=False,
            response_to_player="",
            needs_check=False,
            check_type=None,
            check_attributes=[],
            check_target=None,
            difficulty="常规",
            action_description=player_input,
            npc_response_needed=False,
            npc_actor_id=None,
            npc_intent=None,
        )


class TriggerAwareStateAgent(DummyStateAgent):
    def __init__(self):
        super().__init__()
        self.npc_calls = 0
        self.triggers = []

    def evolve_npc_action(self, npc_id, game_state, check_result=None, npc_intent=None, additional_context=None):
        self.npc_calls += 1
        trigger = None
        if additional_context:
            trigger = additional_context.get("trigger")
        self.triggers.append(trigger)
        return StateEvolutionOutput(
            narrative="守卫观察着你的举动。",
            changes=[],
            resolved=True,
            next_action_hint=None,
            is_end=False,
            end_narrative="",
        )


class AddDescriptionStateAgent(DummyStateAgent):
    def evolve_player_action(self, check_result, action_description, game_state, additional_context=None):
        return StateEvolutionOutput(
            narrative="你在墙上发现了新的刻痕。",
            changes=[
                StateChange(
                    id="map-room-library-01",
                    field="description.public",
                    operation=ChangeOperation.ADD,
                    value={"description": "墙面上多了一行潮湿的划痕"},
                )
            ],
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
        self.assertEqual(bundle.npc_response_mode, "queue")
        self.assertIn("char-player-01", bundle.game_state.characters)
        self.assertIn("map-room-library-01", bundle.game_state.maps)

    def test_apply_world_settings_can_override_npc_mode(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=DummyStateAgent(),
            npc_response_mode="queue",
        )

        engine.apply_world_settings(
            world_name=bundle.world_name,
            end_condition=bundle.end_condition,
            npc_response_mode="reactive",
        )
        self.assertEqual(engine._npc_response_mode, "reactive")

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

    def test_alias_player_id_change_is_normalized(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=AliasIdStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("拿起煤油灯")
        self.assertTrue(result["success"])

        player = engine.game_state.get_player()
        self.assertIsNotNone(player)
        self.assertIn("item-lantern-01", player.inventory)

    def test_slash_help_is_treated_as_command(self):
        parser = InputSystem(FakeIO())
        parsed = parser.parse_input("/help")
        self.assertEqual(parsed.input_type, InputType.BASIC_COMMAND)
        self.assertEqual(parsed.command, "help")

    def test_ai_end_review_is_used_before_code_fallback(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=AiEndReviewStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("我停下脚步")
        self.assertTrue(result["game_over"])
        self.assertIn("故事到此结束", result.get("narrative") or "")

    def test_dynamic_action_queue_removes_unavailable_actor(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=DummyStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        guard = engine.game_state.characters.get("char-guard-01")
        self.assertIsNotNone(guard)
        guard.status.hp = 0

        player = engine.game_state.get_player()
        self.assertIsNotNone(player)
        player.status.hp = 10

        queue = engine._build_dynamic_action_queue()
        self.assertNotIn("char-guard-01", queue)
        self.assertIn("char-player-01", queue)

    def test_npc_participates_and_applies_changes_before_player_turn(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = NpcCapableStateAgent()
        rule_system = DummyRuleSystem()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=state_agent,
            rule_system=rule_system,
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        engine._action_queue = ["char-guard-01", "char-player-01"]
        result = engine.process_input("继续前进")

        self.assertTrue(result["success"])
        self.assertGreaterEqual(state_agent.npc_calls, 1)
        self.assertIsNotNone(state_agent.last_check_result)
        self.assertEqual(rule_system.calls, 1)
        self.assertIn("守卫低声提醒你保持安静", result.get("narrative") or "")

        player = engine.game_state.get_player()
        self.assertIsNotNone(player)
        self.assertEqual(player.status.san, 59)

    def test_add_operation_keeps_description_public_as_list(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=AddDescriptionStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("观察墙面")
        self.assertTrue(result["success"])

        current_map = engine.game_state.get_current_map()
        self.assertIsNotNone(current_map)
        self.assertIsInstance(current_map.description.public, list)
        self.assertTrue(current_map.description.get_public_text())

    def test_help_command_should_not_trigger_npc_prelude(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = NpcCapableStateAgent()
        rule_system = DummyRuleSystem()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=state_agent,
            rule_system=rule_system,
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        engine._action_queue = ["char-guard-01", "char-player-01"]
        result = engine.process_input("\\help")

        self.assertTrue(result["success"])
        self.assertIn("基础指令列表", result.get("response") or "")
        self.assertEqual(state_agent.npc_calls, 0)
        self.assertEqual(rule_system.calls, 0)

    def test_move_command_updates_player_location(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=DummyStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        current_map = engine.game_state.get_current_map()
        self.assertIsNotNone(current_map)
        self.assertTrue(current_map.neighbors)
        target_map_id = current_map.neighbors[0].id

        result = engine.process_input(f"\\move to {target_map_id}")
        self.assertTrue(result["success"])
        self.assertIn("移动到了", result.get("response") or "")

        player = engine.game_state.get_player()
        self.assertIsNotNone(player)
        self.assertEqual(player.location, target_map_id)
        self.assertEqual(engine.game_state.current_scene_id, target_map_id)

    def test_move_command_supports_to_equals_map_id(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=DummyStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        current_map = engine.game_state.get_current_map()
        self.assertIsNotNone(current_map)
        self.assertTrue(current_map.neighbors)
        target_map_id = current_map.neighbors[0].id

        result = engine.process_input(f"\\move to={target_map_id}")
        self.assertTrue(result["success"])

        player = engine.game_state.get_player()
        self.assertIsNotNone(player)
        self.assertEqual(player.location, target_map_id)

    def test_io_rejects_invalid_inventory_item_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            io = IOSystem(db_path=tmp_dir, mode="json")

            player = Character(id="char-player-01", name="测试者", is_player=True)
            valid_item = Item(id="item-key-01", name="钥匙")
            self.assertEqual(io.save_character(player), ERROR_SUCCESS)
            self.assertEqual(io.save_item(valid_item), ERROR_SUCCESS)

            ok_change = StateChange(
                id="char-player-01",
                field="inventory",
                operation=ChangeOperation.ADD,
                value="item-key-01",
            )
            self.assertEqual(io.apply_state_change(ok_change), ERROR_SUCCESS)

            bad_change = StateChange(
                id="char-player-01",
                field="inventory",
                operation=ChangeOperation.ADD,
                value="item-not-exist-01",
            )
            self.assertEqual(io.apply_state_change(bad_change), ERROR_ID_NOT_FOUND)

            reloaded_player = io.get_character("char-player-01")
            self.assertIsNotNone(reloaded_player)
            self.assertEqual(reloaded_player.inventory, ["item-key-01"])

    def test_move_command_rejects_non_neighbor(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=DummyStateAgent(),
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("\\move to map-room-secret-01")
        self.assertTrue(result["success"])
        self.assertIn("无法移动到目标", result.get("response") or "")

    def test_reactive_mode_triggers_dm_driven_npc_response(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = NpcCapableStateAgent()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=ReactiveDMAgent(),
            state_agent=state_agent,
            npc_response_mode="reactive",
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("我靠近守卫")
        self.assertTrue(result["success"])
        self.assertIn("守卫低声提醒你保持安静", result.get("narrative") or "")
        self.assertGreaterEqual(state_agent.npc_calls, 1)

    def test_reactive_mode_skips_queue_prelude_when_npc_first(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = TriggerAwareStateAgent()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=ReactiveNoNpcDMAgent(),
            state_agent=state_agent,
            npc_response_mode="reactive",
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        engine._action_queue = ["char-guard-01", "char-player-01"]
        result = engine.process_input("我检查门锁")

        self.assertTrue(result["success"])
        self.assertEqual(state_agent.npc_calls, 0)

    def test_queue_mode_marks_npc_trigger_as_queue(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = TriggerAwareStateAgent()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=DummyDMAgent(),
            state_agent=state_agent,
            npc_response_mode="queue",
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        engine._action_queue = ["char-guard-01", "char-player-01"]
        result = engine.process_input("我观察守卫")

        self.assertTrue(result["success"])
        self.assertGreaterEqual(state_agent.npc_calls, 1)
        self.assertIn("queue", state_agent.triggers)

    def test_reactive_mode_marks_npc_trigger_as_reactive(self):
        bundle = load_initial_world_bundle(FakeIO(), player_name="测试者", world_name="mysterious_library")

        state_agent = TriggerAwareStateAgent()
        engine = GameEngine(
            io_system=FakeIO(),
            dm_agent=ReactiveDMAgent(),
            state_agent=state_agent,
            npc_response_mode="reactive",
        )
        engine.game_state = bundle.game_state
        engine.apply_world_settings(bundle.world_name, bundle.end_condition)

        result = engine.process_input("我靠近守卫")

        self.assertTrue(result["success"])
        self.assertGreaterEqual(state_agent.npc_calls, 1)
        self.assertIn("reactive", state_agent.triggers)


if __name__ == "__main__":
    unittest.main()
