"""
Input系统 - 玩家输入处理模块

负责接收并初步处理玩家输入：
1. 区分基础指令（以\开头）和自然语言
2. 处理基础指令并返回处理结果
3. 将自然语言输入传递给DM Agent
"""

import logging
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from src.data.models import (
    Character, Item, Map, GameState, StateChange, ChangeOperation
)
from src.data.io_system import IOSystem

# 配置日志
logger = logging.getLogger(__name__)


class InputType(Enum):
    """输入类型枚举"""
    BASIC_COMMAND = "basic_command"  # 基础指令
    NATURAL_LANGUAGE = "natural_language"  # 自然语言


@dataclass
class InputResult:
    """输入处理结果"""
    input_type: InputType
    command: Optional[str] = None  # 基础指令类型
    args: Optional[List[str]] = None  # 指令参数
    natural_input: Optional[str] = None  # 自然语言输入
    direct_response: Optional[str] = None  # 直接回复（基础指令处理结果）
    changes: Optional[List[StateChange]] = None  # 状态变更列表


class InputSystem:
    """
    Input系统 - 玩家输入处理器
    
    功能：
    - 解析玩家输入类型
    - 执行基础指令
    - 传递自然语言给DM Agent
    """
    
    # 基础指令列表
    BASIC_COMMANDS = {
        "look": "查看当前场景或指定目标",
        "inventory": "查看背包",
        "pickup": "捡起物品",
        "drop": "放下物品",
        "status": "查看自身状态",
        "save": "保存进度",
        "load": "加载进度",
        "help": "显示帮助",
        "exit": "退出游戏",
    }
    
    def __init__(self, io_system: IOSystem):
        """
        初始化Input系统
        
        Args:
            io_system: IO系统实例，用于数据操作
        """
        self.io = io_system
        logger.info("Input系统初始化完成")
    
    def parse_input(self, user_input: str) -> InputResult:
        """
        解析玩家输入
        
        Args:
            user_input: 原始输入字符串
            
        Returns:
            InputResult: 解析后的输入结果
        """
        user_input = user_input.strip()
        
        if not user_input:
            return InputResult(
                input_type=InputType.BASIC_COMMAND,
                direct_response="请输入指令或自然语言描述。"
            )
        
        # 检查是否为基础指令（以\开头）
        if user_input.startswith("\\"):
            return self._parse_command(user_input[1:])
        
        # 自然语言输入
        return InputResult(
            input_type=InputType.NATURAL_LANGUAGE,
            natural_input=user_input
        )
    
    def _parse_command(self, command_str: str) -> InputResult:
        """
        解析基础指令
        
        Args:
            command_str: 去除\后的指令字符串
            
        Returns:
            InputResult: 解析结果
        """
        parts = command_str.strip().split()
        if not parts:
            return InputResult(
                input_type=InputType.BASIC_COMMAND,
                direct_response="空指令，请输入具体指令。"
            )
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return InputResult(
            input_type=InputType.BASIC_COMMAND,
            command=command,
            args=args,
            natural_input=None
        )
    
    def execute_command(
        self,
        command: str,
        args: List[str],
        game_state: GameState
    ) -> InputResult:
        """
        执行基础指令
        
        Args:
            command: 指令名称
            args: 指令参数
            game_state: 当前游戏状态
            
        Returns:
            InputResult: 包含处理结果和可能的变更
        """
        if command not in self.BASIC_COMMANDS:
            return InputResult(
                input_type=InputType.BASIC_COMMAND,
                command=command,
                args=args,
                direct_response=f"未知指令: {command}。输入 \\help 查看可用指令。",
                changes=[]
            )
        
        # 获取玩家角色
        player = game_state.get_player()
        if not player:
            return InputResult(
                input_type=InputType.BASIC_COMMAND,
                command=command,
                args=args,
                direct_response="错误：未找到玩家角色",
                changes=[]
            )
        
        # 执行对应指令
        handler = getattr(self, f"_cmd_{command}", None)
        if handler:
            response, changes = handler(args, player, game_state)
            return InputResult(
                input_type=InputType.BASIC_COMMAND,
                command=command,
                args=args,
                direct_response=response,
                changes=changes or []
            )
        
        return InputResult(
            input_type=InputType.BASIC_COMMAND,
            command=command,
            args=args,
            direct_response=f"指令 {command} 尚未实现",
            changes=[]
        )
    
    def _cmd_look(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        查看场景或目标
        
        Args:
            args: 查看目标（可选）
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        # 获取当前地图
        current_map = game_state.get_current_map()
        if not current_map:
            return "错误：当前不在任何场景中", changes
        
        # 如果没有指定目标，查看当前场景
        if not args:
            # 构建场景描述
            description = f"【{current_map.name}】\n"
            description += current_map.description.get_public_text() + "\n\n"
            
            # 显示相邻场景
            if current_map.neighbors:
                description += "【可通往】\n"
                for neighbor in current_map.neighbors:
                    description += f"  {neighbor.direction}: {neighbor.description}\n"
            
            # 显示场景中的角色
            if current_map.entities.characters:
                description += "\n【在场角色】\n"
                for char_id in current_map.entities.characters:
                    if char_id != player.id:
                        char = game_state.characters.get(char_id)
                        if char:
                            desc = char.description.get_public_text()
                            description += f"  • {char.name}: {desc[:50]}...\n"
            
            # 显示场景中的物品
            if current_map.entities.items:
                description += "\n【可见物品】\n"
                for item_id in current_map.entities.items:
                    item = game_state.items.get(item_id)
                    if item:
                        desc = item.description.get_public_text()
                        description += f"  • {item.name}: {desc[:50]}...\n"
            
            return description, changes
        
        # 查看指定目标
        target_name = " ".join(args).lower()
        
        # 搜索角色
        for char_id in current_map.entities.characters:
            char = game_state.characters.get(char_id)
            if char and (target_name in char.name.lower() or target_name in char_id.lower()):
                description = f"【{char.name}】\n"
                description += char.description.get_public_text() + "\n"
                description += f"\n状态: HP {char.status.hp}/{char.status.max_hp}, SAN {char.status.san}, 幸运 {char.status.lucky}"
                return description, changes
        
        # 搜索物品
        for item_id in current_map.entities.items:
            item = game_state.items.get(item_id)
            if item and (target_name in item.name.lower() or target_name in item_id.lower()):
                description = f"【{item.name}】\n"
                description += item.description.get_public_text()
                return description, changes
        
        # 搜索玩家背包
        for item_id in player.inventory:
            item = game_state.items.get(item_id)
            if item and (target_name in item.name.lower() or target_name in item_id.lower()):
                description = f"【{item.name}】(在背包中)\n"
                description += item.description.get_public_text()
                return description, changes
        
        return f"未找到目标: {target_name}", changes
    
    def _cmd_inventory(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        查看背包
        
        Args:
            args: 无参数
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        description = f"【{player.name}的背包】\n"
        
        if not player.inventory:
            description += "背包是空的。"
            return description, changes
        
        for item_id in player.inventory:
            item = game_state.items.get(item_id)
            if item:
                desc = item.description.get_public_text()[:30]
                description += f"  • {item.name}: {desc}...\n"
            else:
                description += f"  • [未知物品: {item_id}]\n"
        
        return description, changes
    
    def _cmd_pickup(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        捡起物品
        
        Args:
            args: 物品名称
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        if not args:
            return "请指定要捡起的物品名。用法: \\pickup <物品名>", changes
        
        item_name = " ".join(args).lower()
        current_map = game_state.get_current_map()
        
        if not current_map:
            return "错误：当前不在任何场景中", changes
        
        # 在场景中寻找物品
        for item_id in list(current_map.entities.items):
            item = game_state.items.get(item_id)
            if item and (item_name in item.name.lower() or item_name in item_id.lower()):
                # 检查是否可携带
                if not item.is_portable:
                    return f"{item.name}无法被携带。", changes
                
                # 创建变更：物品位置改为玩家
                changes.append(StateChange(
                    id=item_id,
                    field="location",
                    operation=ChangeOperation.UPDATE,
                    value=player.id
                ))
                
                # 创建变更：从场景移除物品
                new_items = [i for i in current_map.entities.items if i != item_id]
                changes.append(StateChange(
                    id=current_map.id,
                    field="entities.items",
                    operation=ChangeOperation.UPDATE,
                    value=new_items
                ))
                
                # 创建变更：添加到玩家背包
                new_inventory = player.inventory + [item_id]
                changes.append(StateChange(
                    id=player.id,
                    field="inventory",
                    operation=ChangeOperation.UPDATE,
                    value=new_inventory
                ))
                
                return f"你捡起了 {item.name}。", changes
        
        return f"场景中找不到物品: {item_name}", changes
    
    def _cmd_drop(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        放下物品
        
        Args:
            args: 物品名称
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        if not args:
            return "请指定要放下的物品名。用法: \\drop <物品名>", changes
        
        item_name = " ".join(args).lower()
        current_map = game_state.get_current_map()
        
        if not current_map:
            return "错误：当前不在任何场景中", changes
        
        # 在玩家背包中寻找物品
        for item_id in list(player.inventory):
            item = game_state.items.get(item_id)
            if item and (item_name in item.name.lower() or item_name in item_id.lower()):
                # 创建变更：物品位置改为场景
                changes.append(StateChange(
                    id=item_id,
                    field="location",
                    operation=ChangeOperation.UPDATE,
                    value=current_map.id
                ))
                
                # 创建变更：从玩家背包移除
                new_inventory = [i for i in player.inventory if i != item_id]
                changes.append(StateChange(
                    id=player.id,
                    field="inventory",
                    operation=ChangeOperation.UPDATE,
                    value=new_inventory
                ))
                
                # 创建变更：添加到场景
                new_items = current_map.entities.items + [item_id]
                changes.append(StateChange(
                    id=current_map.id,
                    field="entities.items",
                    operation=ChangeOperation.UPDATE,
                    value=new_items
                ))
                
                return f"你放下了 {item.name}。", changes
        
        return f"背包中没有物品: {item_name}", changes
    
    def _cmd_status(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        查看自身状态
        
        Args:
            args: 无参数
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        description = f"【{player.name}】\n"
        description += f"简介: {player.basic_info}\n\n"
        
        # 状态
        description += "【状态】\n"
        description += f"  HP: {player.status.hp}/{player.status.max_hp}\n"
        description += f"  SAN: {player.status.san}/100\n"
        description += f"  幸运: {player.status.lucky}/99\n\n"
        
        # 属性
        description += "【属性】\n"
        description += f"  力量(STR): {player.attributes.str}\n"
        description += f"  体质(CON): {player.attributes.con}\n"
        description += f"  体型(SIZ): {player.attributes.siz}\n"
        description += f"  敏捷(DEX): {player.attributes.dex}\n"
        description += f"  外貌(APP): {player.attributes.app}\n"
        description += f"  智力(INT): {player.attributes.int}\n"
        description += f"  意志(POW): {player.attributes.pow}\n"
        description += f"  教育(EDU): {player.attributes.edu}\n\n"
        
        # 当前位置
        current_map = game_state.get_current_map()
        if current_map:
            description += f"【位置】{current_map.name}\n"
        
        return description, changes
    
    def _cmd_save(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        保存进度
        
        Args:
            args: 存档名（可选）
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        save_name = args[0] if args else "auto_save"
        
        # 这里应该调用IO系统的存档功能
        # 暂时返回提示信息
        return f"游戏进度已保存: {save_name}", changes
    
    def _cmd_load(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        加载进度
        
        Args:
            args: 存档名（可选）
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        save_name = args[0] if args else "auto_save"
        
        # 这里应该调用IO系统的读档功能
        # 暂时返回提示信息
        return f"加载存档功能需要在GameEngine中实现: {save_name}", changes
    
    def _cmd_help(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        显示帮助信息
        
        Args:
            args: 无参数
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        help_text = "【基础指令列表】\n\n"
        help_text += "信息查看类:\n"
        help_text += "  \\look [目标]   - 查看当前场景或指定目标\n"
        help_text += "  \\inventory     - 查看背包\n"
        help_text += "  \\status        - 查看自身状态\n\n"
        
        help_text += "物品操作类:\n"
        help_text += "  \\pickup <物品名> - 捡起物品\n"
        help_text += "  \\drop <物品名>   - 放下物品\n\n"
        
        help_text += "游戏控制类:\n"
        help_text += "  \\save [存档名]   - 保存进度\n"
        help_text += "  \\load [存档名]   - 加载进度\n"
        help_text += "  \\help           - 显示此帮助\n"
        help_text += "  \\exit           - 退出游戏\n\n"
        
        help_text += "【自然语言】\n"
        help_text += "直接输入你想做的事情，例如:\n"
        help_text += "  '我要仔细搜查这个房间'\n"
        help_text += "  '询问守卫关于钥匙的事'\n"
        help_text += "  '用撬棍打开箱子'\n"
        
        return help_text, changes
    
    def _cmd_exit(
        self,
        args: List[str],
        player: Character,
        game_state: GameState
    ) -> Tuple[str, List[StateChange]]:
        """
        退出游戏
        
        Args:
            args: 无参数
            player: 玩家角色
            game_state: 游戏状态
            
        Returns:
            Tuple[描述文本, 变更列表]
        """
        changes = []
        
        return "EXIT_GAME", changes
    
    def get_help_text(self) -> str:
        """获取帮助文本"""
        return self._cmd_help([], None, None)[0]


# 导出
__all__ = ["InputSystem", "InputResult", "InputType"]
