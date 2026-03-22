"""
Game Engine核心模块 - 游戏引擎主类

整合所有模块的主引擎类：
- 游戏状态管理
- 回合循环（7步流程）
- 协调各模块工作

参考spec_v2_simplified.md第6.1节的完整游戏流程
"""

import logging
import json
import re
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from src.data.io_system import IOSystem
from src.data.models import (
    Character, Item, Map, GameState, StateChange, ChangeOperation,
    DMAgentOutput, CheckInput, CheckOutput,
    StateEvolutionOutput,
    CheckType, CheckDifficulty
)
from src.agent.input_system import InputSystem, InputResult, InputType
from src.agent.dm_agent import DMAgent
from src.agent.state_evolution import StateEvolution as StateEvolutionAgent
from src.data.init.world_loader import load_initial_world_bundle
try:
    from src.narrative import NarrativeContext, NarrativeEvent
except Exception:  # pragma: no cover - optional module
    NarrativeContext = None
    NarrativeEvent = None
from src.rule.rule_system import RuleSystem

# 配置日志
logger = logging.getLogger(__name__)


class GameEngine:
    """
    游戏引擎 - 核心控制器
    
    职责：
    1. 管理游戏状态
    2. 执行7步回合流程
    3. 协调Input、DM Agent、规则系统、状态推演系统
    4. 处理存档/读档
    """
    
    def __init__(
        self,
        io_system: Optional[IOSystem] = None,
        input_system: Optional[InputSystem] = None,
        dm_agent: Optional[DMAgent] = None,
        rule_system: Optional[RuleSystem] = None,
        state_agent: Optional[StateEvolutionAgent] = None,
        db_path: str = "data/game.db",
        npc_response_mode: str = "queue",
        narrative_window: int = 5,
    ):
        """
        初始化游戏引擎
        
        Args:
            io_system: IO系统实例（可选）
            input_system: Input系统实例（可选）
            dm_agent: DM Agent实例（可选）
            rule_system: 规则系统实例（可选）
            state_agent: 状态推演Agent实例（可选）
            db_path: 数据库路径
        """
        # 初始化各子系统
        self.io = io_system or IOSystem(db_path=db_path, mode="sqlite")
        self.input_system = input_system or InputSystem(self.io)
        self.dm_agent = dm_agent or DMAgent()
        self.rule_system = rule_system or RuleSystem()
        self.state_agent = state_agent or StateEvolutionAgent()
        
        # 游戏状态
        self.game_state = GameState()
        self._current_narrative = ""  # 当前回合叙事
        self._ending_text = ""  # 结局文本
        self._is_game_over = False
        self.narrative_context = self._create_narrative_context(window_size=narrative_window)
        self.dm_dialogue_log: List[Dict[str, str]] = []  # DM与玩家对话记录
        self._pending_npc_action_plans: Dict[str, Any] = {}
        
        # 回合管理
        self._action_queue: List[str] = []  # 可行动角色队列
        self._current_actor_id: Optional[str] = None  # 当前行动角色
        self._npc_response_mode: str = "queue"
        self.set_npc_response_mode(npc_response_mode)
        
        # 世界配置（可被外部加载器覆盖）
        self.world_name = "default"#修改建议:检查一下各个默认值是否统一
        self.end_condition = "玩家死亡或达成剧情结局"
        self._ending_rules: List[Dict[str, Any]] = []
        
        logger.info("游戏引擎初始化完成")
    
    # ============================================================
    # 游戏生命周期管理
    # ============================================================
    
    def new_game( #修改建议:检查一下这个函数用到没有,main.py里有一个start_new_game 这儿又有一个,思考一下需不需要统一接口
        self,
        world_name: str = "mysterious_library"
    ) -> bool:
        """
        开始新游戏
        
        Args:
            world_name: 世界配置目录名
            
        Returns:
            是否成功启动
        """
        logger.info(f"开始新游戏，世界: {world_name}")
        
        try:
            # 清空现有状态
            self.game_state = GameState()
            self._is_game_over = False
            self._ending_text = ""
            self._current_narrative = ""
            self.narrative_context = self._create_narrative_context(
                window_size=getattr(self.narrative_context, "window_size", 5) if self.narrative_context else 5
            )
            self._pending_npc_action_plans = {}
            
            bundle = load_initial_world_bundle(
                self.io,
                player_name=None,
                world_name=world_name
            )
            self.game_state = bundle.game_state
            self.apply_world_settings(
                bundle.world_name,
                bundle.end_condition,
                bundle.npc_response_mode,
            )
            
            # 初始化回合
            self.game_state.turn_count = 1
            
            logger.info("新游戏启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动新游戏失败: {e}")
            return False
    
    def load_game(self, save_name: str = "auto_save") -> bool:
        """
        加载存档
        
        Args:
            save_name: 存档名称
            
        Returns:
            是否成功加载
        """
        logger.info(f"加载存档: {save_name}")
        
        try:
            # 从IO系统加载游戏状态
            # 这里需要实现具体的存档加载逻辑
            # 暂时使用JSON模式加载
            import json
            save_path = Path(f"data/saves/{save_name}.json")
            
            if not save_path.exists():
                logger.warning(f"存档不存在: {save_path}")
                return False
            
            with open(save_path, "r", encoding="utf-8") as f:
                save_data = json.load(f)
            self.dm_dialogue_log = save_data.pop("dm_dialogue_log", [])
            self._restore_narrative_context(save_data.pop("narrative_context", None))
            
            # 恢复游戏状态
            self.game_state = GameState(**save_data)
            self._is_game_over = False
            
            logger.info("存档加载成功")
            return True
            
        except Exception as e:
            logger.error(f"加载存档失败: {e}")
            return False
    
    def save_game(self, save_name: str = "auto_save") -> bool:
        """
        保存游戏
        
        Args:
            save_name: 存档名称
            
        Returns:
            是否成功保存
        """
        logger.info(f"保存游戏: {save_name}")
        
        try:
            import json
            save_dir = Path("data/saves")
            save_dir.mkdir(parents=True, exist_ok=True)
            
            save_path = save_dir / f"{save_name}.json"
            
            # 序列化游戏状态
            save_data = self.game_state.model_dump()
            save_data["dm_dialogue_log"] = self.dm_dialogue_log
            narrative_state = self._dump_narrative_context()
            if narrative_state:
                save_data["narrative_context"] = narrative_state
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            logger.info("游戏保存成功")
            return True
            
        except Exception as e:
            logger.error(f"保存游戏失败: {e}")
            return False
    
    def restart(self):
        """重新开始游戏"""
        target_world = self.world_name if self.world_name else "mysterious_library"
        self.new_game(target_world)

    def apply_world_settings(
        self,
        world_name: str,
        end_condition: str,
        npc_response_mode: Optional[str] = None,
    ):
        """应用世界级配置（例如来自world.json）。"""
        self.world_name = world_name
        self.end_condition = end_condition or self.end_condition
        if npc_response_mode:
            self.set_npc_response_mode(npc_response_mode)
        # 让状态推演系统共享同一结局条件
        self.state_agent.end_condition = self.end_condition
        self._load_ending_rules()
    
    # ============================================================
    # 核心游戏循环
    # ============================================================
    
    def process_input(self, user_input: str) -> Dict[str, Any]:
        """
        处理玩家输入 - 主入口
        
        执行完整的7步回合流程：
        Step 1: 回合开始 - 清空current_event
        Step 2: 获取行动意图 - 解析输入
        Step 3: DM Agent解析
        Step 4: 规则系统鉴定（如果需要）
        Step 5: 状态推演系统
        Step 6: 应用状态变更
        Step 7: 回合结束
        
        Args:
            user_input: 玩家输入
            
        Returns:
            处理结果字典
        """
        result = {
            "response": None,
            "check_result": None,
            "narrative": None,
            "success": True,
            "game_over": False
        }
        
        try:
            # ===== Step 1: 回合开始 =====
            self._turn_start()
            
            # ===== Step 2: 获取行动意图 =====
            input_result = self.input_system.parse_input(user_input)
            
            # 如果是基础指令，直接处理
            if input_result.input_type == InputType.BASIC_COMMAND:
                if input_result.command:
                    cmd_result = self.input_system.execute_command(
                        input_result.command,
                        input_result.args or [],
                        self.game_state
                    )

                    # 处理需要引擎执行的系统命令
                    if input_result.command == "save":
                        save_name = input_result.args[0] if input_result.args else "auto_save"
                        ok = self.save_game(save_name)
                        cmd_result.direct_response = f"游戏进度已保存: {save_name}" if ok else f"保存失败: {save_name}"

                    if input_result.command == "load":
                        save_name = input_result.args[0] if input_result.args else "auto_save"
                        ok = self.load_game(save_name)
                        cmd_result.direct_response = f"加载存档成功: {save_name}" if ok else f"加载存档失败: {save_name}"
                    
                    # 检查退出指令
                    if cmd_result.direct_response == "EXIT_GAME":
                        result["response"] = "游戏已退出"
                        result["game_over"] = True
                        self._is_game_over = True
                        return result

                    if cmd_result.direct_response == "RESET_GAME":
                        self.restart()
                        result["response"] = "游戏已重置并重新开始"
                        return result

                    if cmd_result.direct_response == "DEBUG_MODE_ON":
                        logging.getLogger().setLevel(logging.DEBUG)
                        result["response"] = "调试模式已开启"
                        return result

                    if cmd_result.direct_response == "DEBUG_MODE_OFF":
                        logging.getLogger().setLevel(logging.INFO)  #修改建议:没有提供关闭调试指令的'\'指令
                        result["response"] = "调试模式已关闭"
                        return result
                    
                    # 应用基础指令产生的变更
                    if cmd_result.changes:
                        self._apply_changes(cmd_result.changes)
                    
                    result["response"] = cmd_result.direct_response
                    return result
                else:
                    result["response"] = input_result.direct_response or "未知指令"
                    return result

            npc_prelude = {"game_over": False, "narrative": ""}
            if self._npc_response_mode == "queue":
                npc_prelude = self._process_npc_turns_until_player()
            npc_prelude_text = (npc_prelude.get("narrative") or "").strip()
            if npc_prelude.get("game_over"):
                result["game_over"] = True
                result["narrative"] = npc_prelude.get("narrative")
                return result
            
            # 自然语言输入，继续DM Agent处理
            natural_input = input_result.natural_input
            
            # ===== Step 3: DM Agent解析 =====
            dm_output = self._dm_agent_parse(
                natural_input,
                npc_prelude_text=npc_prelude_text,
            )
            
            # 如果是纯对话，直接回复
            if dm_output.is_dialogue:
                result["response"] = dm_output.response_to_player
                if npc_prelude_text and result["response"]:
                    result["response"] = f"{npc_prelude_text}\n{result['response']}"
                self._record_dm_dialogue(natural_input, dm_output.response_to_player)
                return result
            
            check_output = None
            
            # ===== Step 4: 规则系统鉴定 =====
            if dm_output.needs_check:
                check_output = self._execute_check(dm_output)
                result["check_result"] = check_output
            
            # ===== Step 5: 状态推演系统 =====
            evolution_result = self._state_evolution(
                dm_output=dm_output,
                check_result=check_output
            )
            
            result["narrative"] = evolution_result.narrative
            if npc_prelude_text and result["narrative"]:
                result["narrative"] = f"{npc_prelude_text}\n{result['narrative']}"
            self._current_narrative = evolution_result.narrative
            self._record_dm_dialogue(natural_input, evolution_result.narrative)
            self._append_narrative_event(
                actor_id=self.game_state.player_id or "",
                actor_name=self.game_state.get_player().name if self.game_state.get_player() else "",
                text=evolution_result.narrative,
                source="player_action",
            )
            
            # ===== Step 6: 应用状态变更 =====
            if evolution_result.changes:
                self._apply_changes(evolution_result.changes)

            # 响应模式：由DM决定是否触发NPC在本轮追响应答。
            if self._npc_response_mode == "reactive":
                npc_follow = self._process_reactive_npc_response(
                    dm_output=dm_output,
                    player_check=check_output,
                )

                npc_text = (npc_follow.get("narrative") or "").strip()
                if npc_text:
                    if result["narrative"]:
                        result["narrative"] = f"{result['narrative']}\n{npc_text}"
                    else:
                        result["narrative"] = npc_text

                if npc_follow.get("game_over"):
                    self._is_game_over = True
                    result["game_over"] = True
                    end_text = npc_follow.get("ending") or ""
                    if end_text:
                        result["narrative"] = f"{result['narrative']}\n\n{end_text}" if result["narrative"] else end_text
            
            # 更新玩家current_event
            player = self.game_state.get_player()
            if player:
                player.memory.current_event = evolution_result.narrative
            
            # 结局判定采用双轨：AI主判定，代码规则保底。
            if evolution_result.is_end:
                self._is_game_over = True
                self._ending_text = evolution_result.end_narrative or self._evaluate_configured_endings()
                result["game_over"] = True
                if self._ending_text:
                    result["narrative"] += f"\n\n{self._ending_text}"
            else:
                ai_end = None
                if hasattr(self.state_agent, "check_end_condition"):
                    try:
                        ai_end = self.state_agent.check_end_condition(self.game_state)
                    except Exception as e:
                        logger.warning(f"AI结局复核失败，回退代码保底: {e}")

                if ai_end and ai_end.is_end:
                    self._is_game_over = True
                    self._ending_text = ai_end.end_narrative or self._evaluate_configured_endings()
                    result["game_over"] = True
                    if self._ending_text:
                        result["narrative"] += f"\n\n{self._ending_text}"
                else:
                    config_ending_text = self._evaluate_configured_endings()
                    if config_ending_text:
                        self._is_game_over = True
                        self._ending_text = config_ending_text
                        result["game_over"] = True
                        result["narrative"] += f"\n\n{self._ending_text}"
            
            # ===== Step 7: 回合结束 =====
            self._turn_end(resolved=evolution_result.resolved)
            
        except Exception as e:
            logger.error(f"处理输入时发生错误: {e}")
            result["success"] = False
            result["response"] = f"系统错误: {str(e)}"
        
        return result
    
    def _turn_start(self):
        """回合开始 - Step 1"""
        # 通过IO层统一清空事件并入log，保持内存与持久层一致
        self.io.clear_current_events()
        for char in self.game_state.characters.values():
            char.memory.clear_current()
        
        # 初始化或维护行动队列
        if not self._action_queue:
            self._refresh_action_queue()
        
        # 获取当前行动者
        if self._action_queue:
            self._current_actor_id = self._action_queue[0]
        else:
            self._current_actor_id = self.game_state.player_id
        
        logger.debug(f"第 {self.game_state.turn_count} 回合开始，当前行动者: {self._current_actor_id}")

    def _process_npc_turns_until_player(self) -> Dict[str, Any]:
        """在玩家输入前处理连续NPC回合，直到轮到玩家或游戏结束。"""
        narratives: List[str] = []
        max_steps = 1

        if not hasattr(self.state_agent, "evolve_npc_action"):
            self._current_actor_id = self.game_state.player_id
            return {
                "game_over": False,
                "narrative": ""
            }

        for _ in range(max_steps):
            if self.is_player_turn() or not self._current_actor_id:
                break

            actor = self.get_current_actor()
            if not actor or actor.is_player or not self._can_actor_act(actor):
                self._turn_end(resolved=True)
                self._turn_start()
                continue

            npc_check = self._execute_npc_check(actor)
            planned_action = self._pending_npc_action_plans.pop(actor.id, None)

            npc_output = self.state_agent.evolve_npc_action(
                npc_id=actor.id,
                game_state=self.game_state,
                check_result=npc_check,
                npc_intent=self._extract_npc_intent_from_plan(planned_action),
                additional_context=self._build_npc_runtime_context(
                    trigger="queue",
                    npc_action_plan=planned_action,
                ),
            )

            if npc_output.changes:
                self._apply_changes(npc_output.changes)

            if npc_output.narrative:
                narratives.append(f"[{actor.name}] {npc_output.narrative}")
                self._append_narrative_event(
                    actor_id=actor.id,
                    actor_name=actor.name,
                    text=npc_output.narrative,
                    source="npc_queue",
                )

            if npc_output.is_end:
                self._is_game_over = True
                self._ending_text = npc_output.end_narrative
                ending_text = "\n\n" + self._ending_text if self._ending_text else ""
                return {
                    "game_over": True,
                    "narrative": "\n".join(narratives) + ending_text
                }

            # NPC回合不支持连动，强制收束为一步，避免阻塞玩家输入。
            self._turn_end(resolved=True)
            self._turn_start()

        return {
            "game_over": False,
            "narrative": "\n".join(narratives)
        }

    def _execute_npc_check(self, actor: Character) -> Optional[CheckOutput]:
        """执行NPC回合的基础规则检定。"""
        try:
            check_input = CheckInput(
                check_type=CheckType.REGULAR,
                attributes=["dex"],
                actor_id=actor.id,
                target_id=None,
                difficulty=CheckDifficulty.REGULAR,
            )
            return self.rule_system.execute_check(check_input, self.game_state)
        except Exception as e:
            logger.warning(f"NPC检定失败，回退为无检定推演: actor={actor.id}, err={e}")
            return None
    
    def _dm_agent_parse(self, player_input: str, npc_prelude_text: str = "") -> DMAgentOutput:
        """
        DM Agent解析 - Step 3
        
        Args:
            player_input: 玩家自然语言输入
            
        Returns:
            DM Agent输出
        """
        # 调用DM Agent（由DM内部构建上下文）
        dm_output = self.dm_agent.parse_intent(
            player_input=player_input,
            game_state=self.game_state,
            additional_context=self._build_dm_additional_context(npc_prelude_text=npc_prelude_text)
        )
        
        logger.debug(f"DM Agent解析结果: needs_check={dm_output.needs_check}")
        return dm_output

    def _process_reactive_npc_response(
        self,
        dm_output: DMAgentOutput,
        player_check: Optional[CheckOutput],
    ) -> Dict[str, Any]:
        """响应式NPC流程：仅在DM判定需要时触发。"""
        if not hasattr(self.state_agent, "evolve_npc_action"):
            return {"game_over": False, "narrative": ""}

        if not dm_output.npc_response_needed:
            return {"game_over": False, "narrative": ""}

        action_plan = self._extract_npc_action_plan(dm_output)
        npc_id = (
            self._extract_npc_actor_from_plan(action_plan)
            or dm_output.npc_actor_id
            or self._pick_default_npc_actor()
        )
        if not npc_id:
            logger.debug("响应模式已开启，但未找到可响应NPC")
            return {"game_over": False, "narrative": ""}

        npc = self.game_state.characters.get(npc_id)
        if not npc or npc.is_player or not self._can_actor_act(npc):
            return {"game_over": False, "narrative": ""}

        npc_check = self._execute_npc_check(npc)
        npc_output = self.state_agent.evolve_npc_action(
            npc_id=npc.id,
            game_state=self.game_state,
            check_result=npc_check,
            npc_intent=dm_output.npc_intent or self._extract_npc_intent_from_plan(action_plan),
            additional_context=self._build_npc_runtime_context(
                trigger="reactive",
                player_check=player_check,
                player_action_description=dm_output.action_description,
                npc_action_plan=action_plan,
            ),
        )

        if npc_output.changes:
            self._apply_changes(npc_output.changes)

        if npc_output.narrative:
            self._append_narrative_event(
                actor_id=npc.id,
                actor_name=npc.name,
                text=npc_output.narrative,
                source="npc_reactive",
            )

        return {
            "game_over": npc_output.is_end,
            "narrative": f"[{npc.name}] {npc_output.narrative}" if npc_output.narrative else "",
            "ending": npc_output.end_narrative,
        }

    def _pick_default_npc_actor(self) -> Optional[str]:
        """在响应模式下兜底选取一个同场景可行动NPC。"""
        player = self.game_state.get_player()
        if not player:
            return None

        for char_id, char in self.game_state.characters.items():
            if char.is_player:
                continue
            if char.location != player.location:
                continue
            if self._can_actor_act(char):
                return char_id

        return None
    
    def _execute_check(self, dm_output: DMAgentOutput) -> CheckOutput:
        """
        执行规则鉴定 - Step 4
        
        Args:
            dm_output: DM Agent输出
            
        Returns:
            鉴定结果
        """
        player = self.game_state.get_player()
        
        # 构建鉴定输入
        check_type = CheckType.REGULAR
        if dm_output.check_type == "对抗鉴定":
            check_type = CheckType.OPPOSED
        
        difficulty = CheckDifficulty.REGULAR
        if dm_output.difficulty == "困难":
            difficulty = CheckDifficulty.HARD
        elif dm_output.difficulty == "极难":
            difficulty = CheckDifficulty.EXTREME
        
        check_input = CheckInput(
            check_type=check_type,
            attributes=dm_output.check_attributes,
            actor_id=self.game_state.player_id or "",
            target_id=dm_output.check_target,
            difficulty=difficulty
        )
        
        # 执行鉴定
        check_output = self.rule_system.execute_check(
            check_input,
            self.game_state
        )
        
        logger.debug(f"鉴定结果: {check_output.result}, 骰子: {check_output.dice_roll}")
        return check_output
    
    def _state_evolution(
        self,
        dm_output: DMAgentOutput,
        check_result: Optional[CheckOutput]
    ) -> StateEvolutionOutput:
        """
        状态推演 - Step 5
        
        Args:
            dm_output: DM Agent输出
            check_result: 鉴定结果（可选）
            
        Returns:
            状态推演结果
        """
        # 调用状态推演
        evolution_output = self.state_agent.evolve_player_action(
            check_result=check_result,
            action_description=dm_output.action_description,
            game_state=self.game_state,
            additional_context={
                "engine_context": self._build_game_context(),
                "npc_response_mode": self._npc_response_mode,
                "npc_response_policy": self._describe_npc_mode_policy(),
                "npc_response_expected": bool(
                    self._npc_response_mode == "reactive" and dm_output.npc_response_needed
                ),
                "npc_response_actor_id": dm_output.npc_actor_id,
            }
        )
        
        logger.debug(f"状态推演完成，变更数: {len(evolution_output.changes)}")
        return evolution_output
    
    def _apply_changes(self, changes: List[StateChange]):
        """
        应用状态变更 - Step 6
        
        Args:
            changes: 变更列表
        """
        for change in changes:
            normalized_change = self._normalize_state_change(change)
            error_code = self.io.apply_state_change(normalized_change)
            
            if error_code == 0:
                logger.debug(f"变更应用成功: {normalized_change.id}.{normalized_change.field}")
                
                # 同步更新内存中的游戏状态
                self._sync_state_change(normalized_change)
            else:
                logger.warning(f"变更应用失败: {normalized_change.id}.{normalized_change.field}, 错误码: {error_code}")

    def _normalize_state_change(self, change: StateChange) -> StateChange:
        """对LLM产出的变更做ID容错，避免因格式差异导致变更丢失。"""
        resolved_id = self._resolve_entity_id(change.id)
        if resolved_id == change.id:
            return change

        logger.info(f"变更ID已自动纠正: {change.id} -> {resolved_id}")
        return StateChange(
            id=resolved_id,
            field=change.field,
            operation=change.operation,
            value=change.value,
        )

    def _resolve_entity_id(self, raw_id: str) -> str:
        """将近似ID映射到当前游戏中的真实实体ID。"""
        all_ids = set(self.game_state.characters.keys()) | set(self.game_state.items.keys()) | set(self.game_state.maps.keys())
        if raw_id in all_ids:
            return raw_id

        # 常见玩家别名修正
        if raw_id in {"player_001", "player-001", "player001", "char_player_01"} and self.game_state.player_id:
            return self.game_state.player_id

        def normalize(text: str) -> str:
            return re.sub(r"[^a-z0-9]", "", text.lower())

        target = normalize(raw_id)
        if not target:
            return raw_id

        for entity_id in all_ids:
            if normalize(entity_id) == target:
                return entity_id

        return raw_id
    
    def _sync_state_change(self, change: StateChange):
        """
        同步内存中的状态变更
        
        Args:
            change: 状态变更
        """
        # 根据变更类型更新内存对象
        if change.id in self.game_state.characters:
            char = self.game_state.characters[change.id]
            self._update_entity_field(char, change.field, change.value, change.operation)
        elif change.id in self.game_state.items:
            item = self.game_state.items[change.id]
            self._update_entity_field(item, change.field, change.value, change.operation)
        elif change.id in self.game_state.maps:
            map_obj = self.game_state.maps[change.id]
            self._update_entity_field(map_obj, change.field, change.value, change.operation)

        if (
            change.id == self.game_state.player_id
            and change.operation == ChangeOperation.UPDATE
            and change.field == "location"
            and isinstance(change.value, str)
        ):
            self.game_state.current_scene_id = change.value
    
    def _update_entity_field(self, entity: Any, field: str, value: Any, operation: ChangeOperation):
        """按操作类型更新实体字段。"""
        field_parts = field.split('.')
        
        try:
            current = entity
            for part in field_parts[:-1]:
                current = getattr(current, part)
            
            final_field = field_parts[-1]
            target = getattr(current, final_field)

            if operation == ChangeOperation.UPDATE:
                setattr(current, final_field, value)
            elif operation == ChangeOperation.ADD:
                if isinstance(target, list):
                    target.append(value)
                else:
                    logger.warning(f"ADD操作目标不是列表: {field}")
            elif operation == ChangeOperation.DELETE:
                if isinstance(target, list):
                    if value in target:
                        target.remove(value)
                else:
                    setattr(current, final_field, None)
            else:
                logger.warning(f"未知操作类型: {operation}")
        except AttributeError as e:
            logger.warning(f"更新字段失败: {field}, {e}")
    
    def _turn_end(self, resolved: bool = True):
        """
        回合结束 - Step 7
        
        Args:
            resolved: 回合是否已解决
        """
        if resolved:
            # 回合已解决：动态重算队列，并将刚行动角色放到队尾避免连续行动。
            self._refresh_action_queue(last_actor_id=self._current_actor_id)
            
            # 增加回合数
            self.game_state.turn_count += 1
            
            # 同步到game_state.turn_order
            self.game_state.turn_order = self._action_queue.copy()
            
        else:
            # 回合未解决（连动机制），保持当前行动者
            logger.debug("回合未解决，保持当前行动者")
        
        logger.debug(f"回合结束，当前回合: {self.game_state.turn_count}, 行动队列: {self._action_queue}")

    def _record_dm_dialogue(self, player_input: str, dm_response: str):
        """记录玩家与DM的对话历史。"""
        self.dm_dialogue_log.append({
            "turn": str(self.game_state.turn_count),
            "player_input": player_input,
            "dm_response": dm_response,
        })

    def _create_narrative_context(self, window_size: int = 5):
        """Create a narrative context instance, with a no-op fallback."""
        if NarrativeContext is None:
            return _NullNarrativeContext()
        return NarrativeContext(window_size=window_size)
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _refresh_action_queue(self, last_actor_id: Optional[str] = None):
        """刷新行动队列。"""
        self._action_queue = self._build_dynamic_action_queue(last_actor_id=last_actor_id)

    def _build_dm_additional_context(self, npc_prelude_text: str = "") -> Dict[str, Any]:
        """构建DM解析用的动态上下文。"""
        context: Dict[str, Any] = {
            "npc_response_mode": self._npc_response_mode,
            "npc_response_policy": self._describe_npc_mode_policy(),
            "engine_context": self._build_game_context(),
            "action_queue": self._action_queue,
            "current_actor_id": self._current_actor_id,
            "narrative_context": self._get_narrative_context_for_llm(),
        }
        if npc_prelude_text:
            context["npc_prelude"] = npc_prelude_text
        return context

    def _build_npc_runtime_context(
        self,
        trigger: str,
        player_check: Optional[CheckOutput] = None,
        player_action_description: str = "",
        npc_action_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建NPC推演用的动态上下文，支持queue/reactive双模式。"""
        context: Dict[str, Any] = {
            "engine_context": self._build_game_context(),
            "trigger": trigger,
            "npc_response_mode": self._npc_response_mode,
            "npc_response_policy": self._describe_npc_mode_policy(),
            "action_queue": self._action_queue,
            "current_actor_id": self._current_actor_id,
            "narrative_context": self._get_narrative_context_for_llm(),
        }
        if player_check:
            context["player_check_result"] = player_check.model_dump()
        if player_action_description:
            context["player_action_description"] = player_action_description
        if npc_action_plan:
            context["npc_action_plan"] = npc_action_plan
        return context

    def _describe_npc_mode_policy(self) -> str:
        """返回当前NPC响应模式的策略说明，供Agent动态拼接上下文。"""
        if self._npc_response_mode == "reactive":
            return "reactive: 不执行玩家前置NPC队列；由DM输出的npc_response_*字段决定是否触发本轮NPC追响应答。"
        return "queue: 玩家输入前最多执行1个NPC前置回合；DM输出的npc_response_*字段只作参考，不直接驱动执行。"

    def set_npc_response_mode(self, mode: str):
        """设置NPC响应模式：queue(前置队列) / reactive(按需响应)。"""
        normalized = (mode or "queue").strip().lower()
        if normalized not in {"queue", "reactive"}:
            logger.warning(f"未知NPC响应模式: {mode}，回退为queue")
            normalized = "queue"
        self._npc_response_mode = normalized

    def _build_dynamic_action_queue(self, last_actor_id: Optional[str] = None) -> List[str]:
        """按可行动性与优先级动态构建行动队列。"""
        ranked: List[Tuple[str, float]] = []
        for char_id, actor in self.game_state.characters.items():
            score = self._calculate_actor_priority(actor)
            if score > 0:
                ranked.append((char_id, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        ordered_ids = [char_id for char_id, _ in ranked]

        # 若刚行动角色仍可行动，则放到队尾，避免连续行动。
        if last_actor_id and last_actor_id in ordered_ids:
            ordered_ids.remove(last_actor_id)
            ordered_ids.append(last_actor_id)

        return ordered_ids

    def _calculate_actor_priority(self, actor: Character) -> float:
        """计算角色行动优先级：DEX + HP占比 + SAN占比。"""
        if not self._can_actor_act(actor):
            return 0.0

        max_hp = max(1, actor.status.max_hp)
        hp_ratio = max(0.0, min(1.0, actor.status.hp / max_hp))
        # 当前模型没有max_san字段，默认按100作为满值。
        san_ratio = max(0.0, min(1.0, actor.status.san / 100.0))
        dex_ratio = max(0.0, min(1.0, actor.attributes.dex / 100.0))

        return round((dex_ratio * 0.5) + (hp_ratio * 0.3) + (san_ratio * 0.2), 6)
    
    def _can_actor_act(self, actor: Character) -> bool:
        """检查角色是否还能继续行动"""
        # 检查角色是否存活/有意识
        if actor.status.hp <= 0:
            return False
        if actor.status.san <= 0:
            return False
        return True
    
    def get_current_actor(self) -> Optional[Character]:
        """获取当前行动角色"""
        if self._current_actor_id:
            return self.game_state.characters.get(self._current_actor_id)
        return None
    
    def is_player_turn(self) -> bool:
        """检查是否是玩家回合"""
        return self._current_actor_id == self.game_state.player_id
    
    def _build_game_context(self) -> Dict[str, Any]:
        """构建游戏上下文"""
        current_map = self.game_state.get_current_map()
        player = self.game_state.get_player()

        nearby_characters: List[Dict[str, Any]] = []
        nearby_items: List[Dict[str, Any]] = []

        if current_map:
            for char_id in current_map.entities.characters:
                char = self.game_state.characters.get(char_id)
                if char and char.id != self.game_state.player_id:
                    nearby_characters.append({
                        "id": char.id,
                        "name": char.name,
                        "basic_info": char.basic_info,
                        "location": char.location,
                    })

            for item_id in current_map.entities.items:
                item = self.game_state.items.get(item_id)
                if item:
                    nearby_items.append({
                        "id": item.id,
                        "name": item.name,
                        "location": item.location,
                    })

        return {
            "turn_count": self.game_state.turn_count,
            "player_id": self.game_state.player_id,
            "current_scene_id": self.game_state.current_scene_id,
            "current_location": {
                "id": current_map.id,
                "name": current_map.name,
                "description": current_map.description.get_public_text(),
            } if current_map else None,
            "nearby_characters": nearby_characters,
            "nearby_items": nearby_items,
            "player_status": {
                "hp": player.status.hp,
                "max_hp": player.status.max_hp,
                "san": player.status.san,
                "lucky": player.status.lucky,
            } if player else None,
            "narrative_context": self._dump_narrative_context(),
        }

    def _append_narrative_event(
        self,
        actor_id: str,
        actor_name: str,
        text: str,
        source: str,
    ) -> None:
        self.narrative_context.add_event(
            NarrativeEvent(
                turn=self.game_state.turn_count,
                actor_id=actor_id,
                actor_name=actor_name,
                text=text,
                source=source,
            )
        )

    def _get_narrative_context_for_llm(self) -> str:
        """Return a compact narrative context block for prompt assembly."""
        if not self.narrative_context:
            return ""
        if hasattr(self.narrative_context, "get_context_for_llm"):
            return self.narrative_context.get_context_for_llm()
        return ""

    def _dump_narrative_context(self) -> Dict[str, Any]:
        """Serialize narrative context for save files."""
        if not self.narrative_context:
            return {}
        if hasattr(self.narrative_context, "export_state"):
            return self.narrative_context.export_state()
        return {}

    def _restore_narrative_context(self, payload: Any) -> None:
        """Restore narrative context from a saved snapshot or dict."""
        if not payload:
            self.narrative_context = self._create_narrative_context()
            return

        if isinstance(payload, dict):
            ctx = self._create_narrative_context(window_size=int(payload.get("window_size", 5) or 5))
            for event_data in payload.get("recent_events", []):
                try:
                    ctx.add_event(NarrativeEvent(**event_data))
                except Exception:
                    continue
            self.narrative_context = ctx
            return

        self.narrative_context = self._create_narrative_context()

    def _load_ending_rules(self):
        """加载世界配置中的结局规则。"""
        endings_dir = Path("config/world") / self.world_name / "endings"
        self._ending_rules = []

        if not endings_dir.exists() or not endings_dir.is_dir():
            return

        for ending_file in sorted(endings_dir.glob("*.json")):
            try:
                with open(ending_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._ending_rules.append(data)
            except Exception as e:
                logger.warning(f"读取结局配置失败: {ending_file}, {e}")

        self._ending_rules.sort(key=lambda x: x.get("priority", 0), reverse=True)

    def _evaluate_configured_endings(self) -> str:
        """评估配置结局，命中返回结局文本，否则返回空字符串。"""
        if not self._ending_rules:
            return ""

        for ending in self._ending_rules:
            condition_expr = str(ending.get("condition_expr", "")).strip()
            if not condition_expr:
                continue

            if self._evaluate_condition_expr(condition_expr):
                return str(ending.get("end_narrative", "")).strip()

        return ""

    def _evaluate_condition_expr(self, expr: str) -> bool:
        """评估简易结局表达式。"""
        player = self.game_state.get_player()
        if not player:
            return False

        # all(a,b,c)
        if expr.startswith("all(") and expr.endswith(")"):
            args = self._split_expr_args(expr[4:-1])
            return all(self._evaluate_condition_expr(a) for a in args)

        # any(a,b,c)
        if expr.startswith("any(") and expr.endswith(")"):
            args = self._split_expr_args(expr[4:-1])
            return any(self._evaluate_condition_expr(a) for a in args)

        # 基础内置条件
        if expr == "player_hp_le_0":
            return player.status.hp <= 0
        if expr == "player_san_le_0":
            return player.status.san <= 0

        if expr.startswith("player_at:"):
            map_id = expr.split(":", 1)[1].strip()
            return player.location == map_id

        if expr.startswith("has_item:"):
            item_id = expr.split(":", 1)[1].strip()
            return item_id in player.inventory

        return False

    def _split_expr_args(self, raw: str) -> List[str]:
        """按最外层逗号拆分表达式参数。"""
        args: List[str] = []
        depth = 0
        buf: List[str] = []

        for ch in raw:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)

            if ch == "," and depth == 0:
                part = "".join(buf).strip()
                if part:
                    args.append(part)
                buf = []
                continue

            buf.append(ch)

        tail = "".join(buf).strip()
        if tail:
            args.append(tail)

        return args
    
    # ============================================================
    # 查询方法
    # ============================================================
    
    def get_game_state(self) -> GameState:
        """获取当前游戏状态"""
        return self.game_state
    
    def is_game_over(self) -> bool:
        """检查游戏是否结束"""
        return self._is_game_over
    
    def get_ending_text(self) -> str:
        """获取结局文本"""
        return self._ending_text
    
    def get_current_narrative(self) -> str:
        """获取当前叙事"""
        return self._current_narrative

    def _extract_npc_intent_from_plan(self, action_plan: Any) -> str:
        """Extract intent description from NPC action plan."""
        if not action_plan:
            return ""
        if isinstance(action_plan, dict):
            return action_plan.get("intent_description", "")
        if hasattr(action_plan, "intent_description"):
            return str(action_plan.intent_description)
        return ""


# ============================================================
# Null Narrative Context Fallback
# ============================================================

class _NullNarrativeContext:
    """Fallback when NarrativeContext is not available."""

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self.recent_events: List[Any] = []
        self.summary_lines: List[str] = []
        self.key_facts: set = set()
        self.summary: str = ""

    def add_event(self, event: Any) -> None:
        """No-op event addition."""
        pass

    def get_context_for_llm(self) -> str:
        """Return empty context for LLM prompts."""
        return ""

    def export_state(self) -> Dict[str, Any]:
        """Return empty state for serialization."""
        return {}


# ============================================================
# 便捷函数
# ============================================================

def create_game_engine(
    db_path: str = "data/game.db",
    **kwargs
) -> GameEngine:
    """
    创建游戏引擎实例
    
    Args:
        db_path: 数据库路径
        **kwargs: 其他配置参数
        
    Returns:
        GameEngine实例
    """
    return GameEngine(db_path=db_path, **kwargs)


# 导出
__all__ = [
    "GameEngine",
    "create_game_engine"
]


# 测试入口
if __name__ == "__main__":
    # 简单测试
    engine = create_game_engine()
    print("GameEngine模块测试完成")
