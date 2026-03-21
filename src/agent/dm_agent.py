"""
DM Agent模块 - 意图解析与鉴定判断

该模块负责解析玩家的自然语言输入，判断：
1. 是否为纯对话（is_dialogue）
2. 是否需要鉴定（needs_check）
3. 鉴定类型（check_type）
4. 鉴定属性（check_attributes）
5. 对抗目标（check_target）
6. 生成行动描述（action_description）

使用方法:
    from src.agent.dm_agent import DMAgent
    from src.data.models import DMAgentInput, GameState
    
    agent = DMAgent()
    
    # 解析玩家意图
    result = agent.parse_intent(
        player_input="我要仔细搜查这个房间",
        game_state=game_state
    )
    
    # result是DMAgentOutput对象
    print(result.needs_check)  # True
    print(result.check_type)   # "非对抗鉴定"
"""

import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from src.data.models import (
    DMAgentInput,
    DMAgentOutput,
    GameState,
    Character,
    Map,
)
from src.agent.llm_service import LLMService, LLMConfig

# 配置日志
logger = logging.getLogger(__name__)

# DMAgentOutput的JSON Schema（用于LLM输出约束）
DMAGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_dialogue": {
            "type": "boolean",
            "description": "是否为纯对话，不需要游戏机制介入"
        },
        "response_to_player": {
            "type": "string",
            "description": "如果是纯对话，直接回复玩家"
        },
        "needs_check": {
            "type": "boolean",
            "description": "是否需要鉴定（掷骰子）"
        },
        "check_type": {
            "type": "string",
            "enum": ["非对抗鉴定", "对抗鉴定"],
            "description": "鉴定类型"
        },
        "check_attributes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "相关属性/技能列表，按相关度排序"
        },
        "check_target": {
            "type": ["string", "null"],
            "description": "对抗目标ID或描述，非对抗鉴定为null"
        },
        "difficulty": {
            "type": "string",
            "enum": ["常规", "困难", "极难"],
            "description": "非对抗鉴定的难度"
        },
        "action_description": {
            "type": "string",
            "description": "行动的自然语言描述，用于后续叙事生成"
        }
    },
    "required": [
        "is_dialogue",
        "response_to_player",
        "needs_check",
        "action_description"
    ]
}


class DMAgent:
    """
    DM Agent - COC游戏主持人智能体
    
    负责解析玩家输入，判断意图类型，决定是否需要鉴定。
    使用LLM服务进行意图识别，通过Prompt工程实现。
    
    Attributes:
        llm_service: LLM服务实例
        system_prompt: 系统提示词
        max_history: 保留的最大对话历史轮数
    
    Example:
        >>> agent = DMAgent()
        >>> result = agent.parse_intent("我要搜查房间", game_state)
        >>> print(result.check_type)
        '非对抗鉴定'
    """
    
    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        system_prompt: Optional[str] = None,
        max_history: int = 5
    ):
        """
        初始化DM Agent
        
        Args:
            llm_service: LLM服务实例，如果为None则自动创建
            system_prompt: 自定义系统提示词，如果为None则加载默认提示词
            max_history: 保留的最大对话历史轮数
        """
        # 初始化LLM服务
        self.llm_service = llm_service or LLMService()
        
        # 加载系统提示词
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            self.system_prompt = self._load_default_system_prompt()
        
        # 配置参数
        self.max_history = max_history
        
        logger.info("DM Agent初始化完成")
    
    def _load_default_system_prompt(self) -> str:
        """
        加载默认系统提示词
        
        Returns:
            系统提示词内容
        """#修改建议:使用统一接口,如果读取失败直接报错,不要搞多余的接口,多余的冗余,容易成屎山代码
        try:
            # 从prompt模块加载
            from src.agent.prompt import load_system_prompt
            return load_system_prompt()
        except ImportError:
            logger.warning("无法从prompt模块加载系统提示词，尝试直接读取文件")
        
        # 直接读取文件
        prompt_path = Path(__file__).parent / "prompt" / "system_prompt.md"
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"系统提示词文件不存在: {prompt_path}")
            # 返回一个基本的备用提示词
            return self._get_fallback_system_prompt()
    
    def _get_fallback_system_prompt(self) -> str:#修改建议:无用降级策略,就算你读了备用提示词游戏就能正常游玩吗?,鉴定为直接删除,改为终止并报错
        """
        获取备用系统提示词（当文件不存在时使用）
        
        Returns:
            备用系统提示词
        """
        return """你是COC游戏主持人。请解析玩家输入，判断：
1. is_dialogue: 是否为纯对话
2. needs_check: 是否需要鉴定
3. check_type: 鉴定类型（"非对抗鉴定"/"对抗鉴定"）
4. check_attributes: 相关属性列表
5. check_target: 对抗目标（如有）
6. difficulty: 难度（"常规"/"困难"/"极难"）
7. action_description: 行动描述

请以JSON格式返回。"""
    
    def parse_intent(
        self,
        player_input: str,
        game_state: Optional[GameState] = None,
        dialogue_history: Optional[List[str]] = None
    ) -> DMAgentOutput:
        """
        解析玩家意图
        
        这是DM Agent的核心方法，分析玩家输入并返回结构化结果。
        
        Args:
            player_input: 玩家的自然语言输入
            game_state: 当前游戏状态（用于构建上下文）
            dialogue_history: 对话历史列表（可选）
        
        Returns:
            DMAgentOutput对象，包含意图解析结果
        
        Raises:
            Exception: 当LLM调用失败时可能抛出异常
        
        Example:
            >>> result = agent.parse_intent("我要开锁", game_state)
            >>> if result.needs_check:
            ...     print(f"需要{result.check_type}")
        """
        # 构建游戏上下文
        game_context = self._build_game_context(game_state)
        
        # 截断对话历史
        if dialogue_history:
            dialogue_history = dialogue_history[-self.max_history:]
        else:
            dialogue_history = []
        
        # 构建完整提示词
        prompt = self._build_prompt(
            system_prompt=self.system_prompt,
            player_input=player_input,
            game_context=game_context,
            dialogue_history=dialogue_history
        )
        
        # 调用LLM进行意图识别
        try:
            response = self.llm_service.call_llm_json(
                prompt=prompt,
                schema=DMAGENT_OUTPUT_SCHEMA,
                temperature=0.3  # 使用较低温度以获得更稳定的输出
            )
            
            if not response.get("success"):
                error_msg = response.get("error", "未知错误")
                logger.error(f"LLM调用失败: {error_msg}")
                return self._create_fallback_output(player_input, error_msg)
            
            # 解析JSON结果
            data = response.get("data", {})
            return self._parse_output(data, player_input)
            
        except Exception as e:
            logger.error(f"解析意图时发生异常: {e}")
            return self._create_fallback_output(player_input, str(e))
    
    def _build_game_context(self, game_state: Optional[GameState]) -> Dict[str, Any]:
        """
        构建游戏上下文信息
        
        从游戏状态中提取相关信息，供LLM进行意图判断。
        
        Args:
            game_state: 游戏状态对象
        
        Returns:
            游戏上下文字典
        """
        if not game_state:
            return {}
        
        context = {
            "current_location": None,
            "current_characters": [],
            "current_items": [],
            "player_info": None,
        }
        
        # 获取当前地图信息
        current_map = game_state.get_current_map()
        if current_map:
            context["current_location"] = {
                "id": current_map.id,
                "name": current_map.name,
                "description": current_map.description.get_public_text(),
            }
            
            # 获取场景中的角色
            for char_id in current_map.entities.characters:
                char = game_state.characters.get(char_id)
                if char:
                    char_info = {
                        "id": char.id,
                        "name": char.name,
                        "is_player": char.is_player,
                        "basic_info": char.basic_info,
                        "description_public": char.description.get_public_text() if char.description else "",
                        "description_hint": char.description.hint if char.description else "",
                    }
                    context["current_characters"].append(char_info)
            
            # 获取场景中的物品
            for item_id in current_map.entities.items:
                item = game_state.items.get(item_id)
                if item:
                    item_info = {
                        "id": item.id,
                        "name": item.name,
                        "description_public": item.description.get_public_text() if item.description else "",
                        "description_hint": item.description.hint if item.description else "",
                        "is_portable": item.is_portable, #缺少位置信息
                    }
                    context["current_items"].append(item_info)
        
        # 获取玩家信息
        player = game_state.get_player()
        if player:
            context["player_info"] = {
                "id": player.id,
                "name": player.name,
                "status": {
                    "hp": player.status.hp,
                    "max_hp": player.status.max_hp,
                    "san": player.status.san,
                },
                "attributes": {
                    "str": player.attributes.str,
                    "con": player.attributes.con,
                    "dex": player.attributes.dex,
                    "int": player.attributes.int,
                    "pow": player.attributes.pow,
                    "edu": player.attributes.edu,
                }
            }
        
        return context
    
    def _build_prompt(
        self,
        system_prompt: str,
        player_input: str,
        game_context: Dict[str, Any],
        dialogue_history: List[str]
    ) -> str:
        """
        构建完整的Prompt
        
        Args:
            system_prompt: 系统提示词
            player_input: 玩家输入
            game_context: 游戏上下文
            dialogue_history: 对话历史
        
        Returns:
            完整的提示词文本
        """
        # 构建游戏上下文文本
        context_text = self._format_game_context(game_context)
        
        # 构建对话历史文本
        history_text = ""
        if dialogue_history:
            history_text = "## 对话历史\n" + "\n".join(dialogue_history) + "\n\n"
        
        # 组合完整提示词
        prompt = f"""{system_prompt}

---

{context_text}

{history_text}
## 玩家输入

"{player_input}"

---

请分析上述玩家输入，按照系统提示词中的要求返回JSON格式的分析结果。
"""
        return prompt
    
    def _format_game_context(self, game_context: Dict[str, Any]) -> str:
        """
        格式化游戏上下文为文本
        
        Args:
            game_context: 游戏上下文字典
        
        Returns:
            格式化后的文本
        """
        if not game_context:
            return "## 游戏上下文\n（无上下文信息）"
        
        lines = ["## 游戏上下文"]
        
        # 当前位置
        location = game_context.get("current_location")
        if location:
            lines.append(f"\n### 当前位置")
            lines.append(f"- 名称: {location.get('name', '未知')}")
            lines.append(f"- 描述: {location.get('description', '无')}")
        
        # 场景中的角色
        characters = game_context.get("current_characters", [])
        if characters:
            lines.append(f"\n### 附近角色")
            for char in characters:
                char_type = "(玩家)" if char.get("is_player") else "(NPC)"
                lines.append(f"- {char.get('name', '未知')} {char_type} [ID: {char.get('id', '?')}]")
                # 添加基本信息
                basic_info = char.get('basic_info', '')
                if basic_info:
                    lines.append(f"  - 简介: {basic_info}")
                # 添加公开描述
                desc_public = char.get('description_public', '')
                if desc_public:
                    lines.append(f"  - 描述: {desc_public}")
        
        # 场景中的物品
        items = game_context.get("current_items", [])
        if items:
            lines.append(f"\n### 附近物品")
            for item in items:
                lines.append(f"- {item.get('name', '未知')} [ID: {item.get('id', '?')}]")
                # 添加公开描述
                desc_public = item.get('description_public', '')
                if desc_public:
                    lines.append(f"  - 描述: {desc_public}")
        
        # 玩家信息
        player_info = game_context.get("player_info")
        if player_info:
            lines.append(f"\n### 玩家角色")
            lines.append(f"- 名称: {player_info.get('name', '未知')}")
            status = player_info.get("status", {})
            lines.append(f"- 状态: HP {status.get('hp', '?')}/{status.get('max_hp', '?')}, SAN {status.get('san', '?')}")
            attrs = player_info.get("attributes", {})
            lines.append(f"- 关键属性: STR{attrs.get('str', '?')}, DEX{attrs.get('dex', '?')}, INT{attrs.get('int', '?')}, POW{attrs.get('pow', '?')}")
        
        return "\n".join(lines)
    
    def _parse_output(
        self,
        data: Dict[str, Any],
        original_input: str
    ) -> DMAgentOutput:
        """
        解析LLM输出为DMAgentOutput对象
        
        Args:
            data: LLM返回的JSON数据
            original_input: 原始玩家输入
        
        Returns:
            DMAgentOutput对象
        """
        try:
            # 确保必填字段存在
            is_dialogue = data.get("is_dialogue", False)
            
            output = DMAgentOutput(
                is_dialogue=is_dialogue,
                response_to_player=data.get("response_to_player", ""),
                needs_check=data.get("needs_check", False),
                check_type=data.get("check_type"),
                check_attributes=data.get("check_attributes", []),
                check_target=data.get("check_target"),
                difficulty=data.get("difficulty", "常规"),
                action_description=data.get("action_description", original_input)
            )
            
            logger.debug(f"意图解析完成: is_dialogue={output.is_dialogue}, needs_check={output.needs_check}")
            return output
            
        except Exception as e:
            logger.error(f"解析输出时发生错误: {e}")
            return self._create_fallback_output(original_input, str(e))
    
    def _create_fallback_output(
        self,
        player_input: str,
        error_message: str
    ) -> DMAgentOutput:
        """
        创建降级输出（当LLM调用失败时使用）
        
        Args:
            player_input: 玩家输入
            error_message: 错误信息
        
        Returns:
            降级DMAgentOutput对象
        """
        logger.warning(f"使用降级输出，错误: {error_message}")
        
        return DMAgentOutput(
            is_dialogue=True,
            response_to_player=f"我理解你的意图是：{player_input}。让我继续游戏。",
            needs_check=False,
            check_type=None,
            check_attributes=[],
            check_target=None,
            difficulty="常规",
            action_description=player_input
        )
    
    def quick_parse(
        self,
        player_input: str,
        **context_kwargs
    ) -> DMAgentOutput:
        """
        快速解析（简化接口）
        
        不需要完整的GameState，可以直接传入上下文信息。
        
        Args:
            player_input: 玩家输入
            **context_kwargs: 上下文关键字参数，如 location, characters等
        
        Returns:
            DMAgentOutput对象
        
        Example:
            >>> result = agent.quick_parse(
            ...     "我要开锁",
            ...     location={"name": "废弃仓库", "description": "阴暗潮湿"},
            ...     characters=[{"name": "守卫", "id": "guard1"}]
            ... )
        """
        game_context = {
            "current_location": context_kwargs.get("location"),
            "current_characters": context_kwargs.get("characters", []),
            "current_items": context_kwargs.get("items", []),
            "player_info": context_kwargs.get("player"),
        }
        
        # 构建提示词
        prompt = self._build_prompt(
            system_prompt=self.system_prompt,
            player_input=player_input,
            game_context=game_context,
            dialogue_history=context_kwargs.get("dialogue_history", [])
        )
        
        # 调用LLM
        try:
            response = self.llm_service.call_llm_json(
                prompt=prompt,
                schema=DMAGENT_OUTPUT_SCHEMA,
                temperature=0.3
            )
            
            if response.get("success"):
                return self._parse_output(response.get("data", {}), player_input)
            else:
                return self._create_fallback_output(player_input, response.get("error", "调用失败"))
                
        except Exception as e:
            return self._create_fallback_output(player_input, str(e))


# 便捷函数

def create_dm_agent(
    llm_service: Optional[LLMService] = None,
    system_prompt: Optional[str] = None
) -> DMAgent:
    """
    创建DM Agent实例的便捷函数
    
    Args:
        llm_service: LLM服务实例
        system_prompt: 自定义系统提示词
    
    Returns:
        DMAgent实例
    """
    return DMAgent(llm_service=llm_service, system_prompt=system_prompt)


def quick_intent_parse(
    player_input: str,
    game_state: Optional[GameState] = None,
    **kwargs
) -> DMAgentOutput:
    """
    快速意图解析（无需预先创建实例）
    
    Args:
        player_input: 玩家输入
        game_state: 游戏状态
        **kwargs: 其他参数
    
    Returns:
        DMAgentOutput对象
    
    Example:
        >>> from src.agent.dm_agent import quick_intent_parse
        >>> result = quick_intent_parse("我要搜查房间", game_state)
        >>> print(result.check_attributes)
    """
    agent = DMAgent()
    return agent.parse_intent(player_input, game_state=game_state, **kwargs)
