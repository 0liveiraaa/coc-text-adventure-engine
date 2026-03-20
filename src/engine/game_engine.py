"""
Game Engine核心模块 - 游戏引擎主类

整合所有模块的主引擎类：
- 游戏状态管理
- 回合循环（7步流程）
- 协调各模块工作

参考spec_v2_simplified.md第6.1节的完整游戏流程
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from src.data.io_system import IOSystem
from src.data.models import (
    Character, Item, Map, GameState, StateChange, ChangeOperation,
    DMAgentInput, DMAgentOutput, CheckInput, CheckOutput,
    StateEvolutionInput, StateEvolutionOutput,
    CheckType, CheckDifficulty
)
from src.agent.input_system import InputSystem, InputResult, InputType
from src.agent.dm_agent import DMAgent
from src.agent.state_evolution import StateEvolutionAgent
from src.agent.prompt import load_system_prompt, load_state_evolution_prompt
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
        db_path: str = "data/game.db"
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
        
        # 回合管理
        self._action_queue: List[str] = []  # 可行动角色队列
        self._current_actor_id: Optional[str] = None  # 当前行动角色
        
        # 配置
        self.end_condition = "玩家死亡或达成剧情结局" #应该读取config/world文件里的设定而非在此处设定
        
        # 加载提示词
        self._system_prompt = load_system_prompt()
        self._state_evolution_prompt = load_state_evolution_prompt()
        
        logger.info("游戏引擎初始化完成")
    
    # ============================================================
    # 游戏生命周期管理
    # ============================================================
    
    def new_game(
        self,
        player_name: str,
        scenario_id: Optional[str] = None
    ) -> bool:
        """
        开始新游戏
        
        Args:
            player_name: 玩家角色名称
            scenario_id: 剧本ID（可选，用于加载预设场景）
            
        Returns:
            是否成功启动
        """
        logger.info(f"开始新游戏，玩家: {player_name}")
        
        try:
            # 清空现有状态
            self.game_state = GameState()
            self._is_game_over = False
            self._ending_text = ""
            self._current_narrative = ""
            
            # 如果有指定剧本，加载剧本数据
            if scenario_id:
                self._load_scenario(scenario_id)
            else:
                # 创建默认场景和角色
                self._create_default_world(player_name)
            
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
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            logger.info("游戏保存成功")
            return True
            
        except Exception as e:
            logger.error(f"保存游戏失败: {e}")
            return False
    
    def restart(self):
        """重新开始游戏"""
        player_name = "调查员"
        if self.game_state.player_id:
            player = self.game_state.get_player()
            if player:
                player_name = player.name
        
        self.new_game(player_name)
    
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
                    
                    # 检查退出指令
                    if cmd_result.direct_response == "EXIT_GAME":
                        result["response"] = "游戏已退出"
                        result["game_over"] = True
                        self._is_game_over = True
                        return result
                    
                    # 应用基础指令产生的变更
                    if cmd_result.changes:
                        self._apply_changes(cmd_result.changes)
                    
                    result["response"] = cmd_result.direct_response
                    
                    # ===== Step 7: 回合结束 =====
                    self._turn_end(resolved=True)
                    return result
                else:
                    result["response"] = input_result.direct_response or "未知指令"
                    return result
            
            # 自然语言输入，继续DM Agent处理
            natural_input = input_result.natural_input
            
            # ===== Step 3: DM Agent解析 =====
            dm_output = self._dm_agent_parse(natural_input)
            
            # 如果是纯对话，直接回复
            if dm_output.is_dialogue:
                result["response"] = dm_output.response_to_player
                
                # 记录到玩家记忆
                player = self.game_state.get_player()
                if player:
                    player.memory.current_event = dm_output.response_to_player
                
                self._turn_end(resolved=True)
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
            self._current_narrative = evolution_result.narrative
            
            # ===== Step 6: 应用状态变更 =====
            if evolution_result.changes:
                self._apply_changes(evolution_result.changes)
            
            # 更新玩家current_event
            player = self.game_state.get_player()
            if player:
                player.memory.current_event = evolution_result.narrative
            
            # 检查游戏结束
            if evolution_result.is_end:
                self._is_game_over = True
                self._ending_text = evolution_result.end_narrative
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
        # 清空所有角色的current_event
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
    
    def _dm_agent_parse(self, player_input: str) -> DMAgentOutput:
        """
        DM Agent解析 - Step 3
        
        Args:
            player_input: 玩家自然语言输入
            
        Returns:
            DM Agent输出
        """
        # 构建DM Agent输入
        dm_input = DMAgentInput(
            system_prompt=self._build_system_prompt(),
            player_input=player_input,
            game_context=self._build_game_context()
        )
        
        # 调用DM Agent
        dm_output = self.dm_agent.parse_intent(dm_input)
        
        logger.debug(f"DM Agent解析结果: needs_check={dm_output.needs_check}")
        return dm_output
    
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
        # 构建状态推演输入
        state_input = StateEvolutionInput(
            system_prompt=self._state_evolution_prompt,
            end_condition=self.end_condition,
            check_result=check_result,
            action_description=dm_output.action_description,
            game_context=self._build_game_context()
        )
        
        # 调用状态推演
        evolution_output = self.state_agent.evolve_state(
            state_input,
            self.game_state
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
            error_code = self.io.apply_state_change(change)
            
            if error_code == 0:
                logger.debug(f"变更应用成功: {change.id}.{change.field}")
                
                # 同步更新内存中的游戏状态
                self._sync_state_change(change)
            else:
                logger.warning(f"变更应用失败: {change.id}.{change.field}, 错误码: {error_code}")
    
    def _sync_state_change(self, change: StateChange):
        """
        同步内存中的状态变更
        
        Args:
            change: 状态变更
        """
        # 根据变更类型更新内存对象
        if change.id in self.game_state.characters:
            char = self.game_state.characters[change.id]
            self._update_entity_field(char, change.field, change.value)
        elif change.id in self.game_state.items:
            item = self.game_state.items[change.id]
            self._update_entity_field(item, change.field, change.value)
        elif change.id in self.game_state.maps:
            map_obj = self.game_state.maps[change.id]
            self._update_entity_field(map_obj, change.field, change.value)
    
    def _update_entity_field(self, entity: Any, field: str, value: Any):
        """更新实体字段"""
        field_parts = field.split('.')
        
        try:
            current = entity
            for part in field_parts[:-1]:
                current = getattr(current, part)
            
            final_field = field_parts[-1]
            setattr(current, final_field, value)
        except AttributeError as e:
            logger.warning(f"更新字段失败: {field}, {e}")
    
    def _turn_end(self, resolved: bool = True):
        """
        回合结束 - Step 7
        
        Args:
            resolved: 回合是否已解决
        """
        if resolved:
            # 回合已解决，处理行动队列
            if self._current_actor_id and self._action_queue:
                # 将当前行动者移到队尾（如果还能继续行动）
                current_actor = self.game_state.characters.get(self._current_actor_id)
                if current_actor and self._can_actor_act(current_actor):
                    # 移到队尾，参与下一回合
                    self._action_queue.append(self._action_queue.pop(0))
                else:
                    # 无法继续行动，从队列移除
                    self._action_queue.pop(0)
            
            # 增加回合数
            self.game_state.turn_count += 1
            
            # 同步到game_state.turn_order
            self.game_state.turn_order = self._action_queue.copy()
            
        else:
            # 回合未解决（连动机制），保持当前行动者
            logger.debug("回合未解决，保持当前行动者")
        
        logger.debug(f"回合结束，当前回合: {self.game_state.turn_count}, 行动队列: {self._action_queue}")
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _refresh_action_queue(self):
        """刷新行动队列"""
        # 从game_state初始化行动队列
        if self.game_state.turn_order:
            self._action_queue = self.game_state.turn_order.copy()
        else:
            # 默认只有玩家
            self._action_queue = [self.game_state.player_id] if self.game_state.player_id else []
    
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
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return self._system_prompt
    
    def _build_game_context(self) -> Dict[str, Any]:
        """构建游戏上下文"""
        return {
            "turn_count": self.game_state.turn_count,
            "player_id": self.game_state.player_id,
            "current_scene_id": self.game_state.current_scene_id,
            "characters_count": len(self.game_state.characters),
            "items_count": len(self.game_state.items),
            "maps_count": len(self.game_state.maps),
        }
    
    def _create_default_world(self, player_name: str):
        """创建默认游戏世界"""
        from src.data.models import (
            CharacterAttributes, CharacterStatus, Description, MapEntities
        )
        
        # 创建玩家角色
        player = Character(
            id="player-001",
            name=player_name,
            basic_info="一位勇敢的调查员",
            description=Description(
                public=[{"description": "一名普通的调查员，正在探索未知的秘密。"}],
                hint=""
            ),
            location="map-library-entrance",
            inventory=[],
            status=CharacterStatus(hp=12, max_hp=12, san=60, lucky=50),
            attributes=CharacterAttributes(
                str=12, con=12, siz=13, dex=10,
                app=11, int=13, pow=12, edu=14
            ),
            is_player=True
        )
        
        # 创建初始场景
        entrance = Map(
            id="map-library-entrance",
            name="图书馆入口",
            description=Description(
                public=[{"description": "古老的图书馆入口，厚重的木门微微敞开，里面传来陈旧纸张的气息。"}],
                hint="这里是一个神秘调查的起点"
            ),
            neighbors=[],
            entities=MapEntities(characters=["player-001"], items=[])
        )
        
        # 添加游戏状态
        self.game_state.characters["player-001"] = player
        self.game_state.maps["map-library-entrance"] = entrance
        self.game_state.player_id = "player-001"
        self.game_state.current_scene_id = "map-library-entrance"
        self.game_state.turn_order = ["player-001"]
        
        # 保存到数据库
        self.io.save_character(player)
        self.io.save_map(entrance)
        
        logger.info("默认世界创建完成")
    
    def _load_scenario(self, scenario_id: str):
        """加载剧本"""
        # TODO: 实现剧本加载逻辑
        logger.info(f"加载剧本: {scenario_id}")
        self._create_default_world("调查员")
    
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
