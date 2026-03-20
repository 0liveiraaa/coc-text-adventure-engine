"""
世界数据加载器

功能：
- 从JSON配置文件加载初始世界数据
- 将数据导入到IO系统中
- 创建GameState实例

使用方法：
    loader = WorldLoader(io_system)
    game_state = loader.load_world_from_config()
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from src.data.models import (
    Character, Item, Map, GameState, Description,
    CharacterAttributes, CharacterStatus, Memory,
    MapNeighbor, MapEntities
)
from src.data.io_system import IOSystem


class WorldLoader:
    """
    世界数据加载器
    
    从config/world/目录下的JSON文件加载初始游戏数据，
    并将其导入到IO系统和GameState中。
    """
    
    def __init__(self, io_system: IOSystem, config_dir: str = "config/world"):
        """
        初始化世界加载器
        
        Args:
            io_system: IO系统实例，用于存储加载的数据
            config_dir: 配置文件目录路径，默认为"config/world"
        """
        self.io = io_system
        self.config_dir = Path(config_dir)
        self._characters: Dict[str, Character] = {}
        self._items: Dict[str, Item] = {}
        self._maps: Dict[str, Map] = {}
    
    def load_world_from_config(self, player_name: Optional[str] = None) -> GameState:
        """
        从配置文件加载完整的世界数据
        
        Args:
            player_name: 玩家自定义名称（可选），如果不提供则使用默认名称
            
        Returns:
            GameState: 初始化好的游戏状态对象
        """
        # 加载各类数据
        self._load_characters(player_name)
        self._load_items()
        self._load_maps()
        
        # 创建GameState
        game_state = GameState(
            characters=self._characters,
            items=self._items,
            maps=self._maps,
            player_id="char-player-01",
            current_scene_id="map-room-library-01",
            turn_order=list(self._characters.keys()),
            turn_count=0,
            is_ended=False
        )
        
        # 将数据保存到IO系统
        self._save_to_io_system()
        
        return game_state
    
    def _load_characters(self, player_name: Optional[str] = None):
        """加载角色数据"""
        file_path = self.config_dir / "characters.json"
        
        if not file_path.exists():
            print(f"[WorldLoader] 警告: 角色配置文件不存在: {file_path}")
            return
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for char_data in data.get("characters", []):
                # 如果提供了玩家名称，更新玩家角色名称
                if player_name and char_data.get("is_player"):
                    char_data["name"] = player_name
                
                # 构建Description对象
                desc_data = char_data.get("description", {})
                description = Description(
                    public=desc_data.get("public", []),
                    hint=desc_data.get("hint", "")
                )
                
                # 构建Attributes对象
                attr_data = char_data.get("attributes", {})
                attributes = CharacterAttributes(
                    str=attr_data.get("str", 10),
                    con=attr_data.get("con", 10),
                    siz=attr_data.get("siz", 10),
                    dex=attr_data.get("dex", 10),
                    app=attr_data.get("app", 10),
                    int=attr_data.get("int", 10),
                    pow=attr_data.get("pow", 10),
                    edu=attr_data.get("edu", 10)
                )
                
                # 构建Status对象
                status_data = char_data.get("status", {})
                status = CharacterStatus(
                    hp=status_data.get("hp", 10),
                    max_hp=status_data.get("max_hp", status_data.get("hp", 10)),
                    san=status_data.get("san", 50),
                    lucky=status_data.get("lucky", 50)
                )
                
                # 构建Memory对象
                memory_data = char_data.get("memory", {})
                memory = Memory(
                    current_event=memory_data.get("current_event", ""),
                    log=memory_data.get("log", [])
                )
                
                # 创建Character对象
                character = Character(
                    id=char_data["id"],
                    name=char_data["name"],
                    basic_info=char_data.get("basic_info", ""),
                    description=description,
                    location=char_data.get("location", ""),
                    inventory=char_data.get("inventory", []),
                    status=status,
                    attributes=attributes,
                    memory=memory,
                    is_player=char_data.get("is_player", False)
                )
                
                self._characters[character.id] = character
            
            print(f"[WorldLoader] 成功加载 {len(self._characters)} 个角色")
            
        except Exception as e:
            print(f"[WorldLoader] 加载角色数据失败: {e}")
            raise
    
    def _load_items(self):
        """加载物品数据"""
        file_path = self.config_dir / "items.json"
        
        if not file_path.exists():
            print(f"[WorldLoader] 警告: 物品配置文件不存在: {file_path}")
            return
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item_data in data.get("items", []):
                # 构建Description对象
                desc_data = item_data.get("description", {})
                description = Description(
                    public=desc_data.get("public", []),
                    hint=desc_data.get("hint", "")
                )
                
                # 创建Item对象
                item = Item(
                    id=item_data["id"],
                    name=item_data["name"],
                    description=description,
                    location=item_data.get("location", ""),
                    is_portable=item_data.get("is_portable", True)
                )
                
                self._items[item.id] = item
            
            print(f"[WorldLoader] 成功加载 {len(self._items)} 个物品")
            
        except Exception as e:
            print(f"[WorldLoader] 加载物品数据失败: {e}")
            raise
    
    def _load_maps(self):
        """加载地图数据"""
        file_path = self.config_dir / "maps.json"
        
        if not file_path.exists():
            print(f"[WorldLoader] 警告: 地图配置文件不存在: {file_path}")
            return
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for map_data in data.get("maps", []):
                # 构建Description对象
                desc_data = map_data.get("description", {})
                description = Description(
                    public=desc_data.get("public", []),
                    hint=desc_data.get("hint", "")
                )
                
                # 构建Neighbors列表
                neighbors = []
                for neighbor_data in map_data.get("neighbors", []):
                    neighbor = MapNeighbor(
                        id=neighbor_data["id"],
                        direction=neighbor_data["direction"],
                        description=neighbor_data.get("description", "")
                    )
                    neighbors.append(neighbor)
                
                # 构建Entities对象
                entities_data = map_data.get("entities", {})
                entities = MapEntities(
                    characters=entities_data.get("characters", []),
                    items=entities_data.get("items", [])
                )
                
                # 创建Map对象
                map_obj = Map(
                    id=map_data["id"],
                    name=map_data["name"],
                    parent_id=map_data.get("parent_id"),
                    description=description,
                    neighbors=neighbors,
                    entities=entities
                )
                
                self._maps[map_obj.id] = map_obj
            
            print(f"[WorldLoader] 成功加载 {len(self._maps)} 个地图")
            
        except Exception as e:
            print(f"[WorldLoader] 加载地图数据失败: {e}")
            raise
    
    def _save_to_io_system(self):
        """将加载的数据保存到IO系统"""
        # 保存角色
        for character in self._characters.values():
            result = self.io.save_character(character)
            if result != 0:
                print(f"[WorldLoader] 警告: 保存角色 {character.id} 失败，错误码: {result}")
        
        # 保存物品
        for item in self._items.values():
            result = self.io.save_item(item)
            if result != 0:
                print(f"[WorldLoader] 警告: 保存物品 {item.id} 失败，错误码: {result}")
        
        # 保存地图
        for map_obj in self._maps.values():
            result = self.io.save_map(map_obj)
            if result != 0:
                print(f"[WorldLoader] 警告: 保存地图 {map_obj.id} 失败，错误码: {result}")
        
        print(f"[WorldLoader] 数据已保存到IO系统")
    
    def get_character(self, char_id: str) -> Optional[Character]:
        """获取指定角色"""
        return self._characters.get(char_id)
    
    def get_item(self, item_id: str) -> Optional[Item]:
        """获取指定物品"""
        return self._items.get(item_id)
    
    def get_map(self, map_id: str) -> Optional[Map]:
        """获取指定地图"""
        return self._maps.get(map_id)
    
    def list_characters(self) -> Dict[str, Character]:
        """获取所有角色"""
        return self._characters.copy()
    
    def list_items(self) -> Dict[str, Item]:
        """获取所有物品"""
        return self._items.copy()
    
    def list_maps(self) -> Dict[str, Map]:
        """获取所有地图"""
        return self._maps.copy()


def load_initial_world(io_system: IOSystem, player_name: Optional[str] = None) -> GameState:
    """
    便捷函数：加载初始世界数据
    
    Args:
        io_system: IO系统实例
        player_name: 玩家自定义名称（可选）
        
    Returns:
        GameState: 初始化好的游戏状态
        
    Example:
        >>> from src.data.io_system import IOSystem
        >>> io = IOSystem(db_path="data/game.db", mode="sqlite")
        >>> game_state = load_initial_world(io, player_name="张三")
    """
    loader = WorldLoader(io_system)
    return loader.load_world_from_config(player_name)
