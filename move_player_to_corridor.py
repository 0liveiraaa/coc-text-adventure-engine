"""
临时脚本：将玩家移动到走廊
用于测试结局系统
"""
import sqlite3
import json

def fix_and_move():
    conn = sqlite3.connect('data/game.db')
    cursor = conn.cursor()
    
    # 1. 修复玩家角色 description.public 格式
    cursor.execute('SELECT id, data FROM characters WHERE id = ?', ('char-player-01',))
    row = cursor.fetchone()
    if row:
        char_id, data = row
        char_data = json.loads(data)
        
        # 修复 description.public
        if isinstance(char_data.get('description', {}).get('public'), dict):
            desc_text = char_data['description']['public'].get('description', '')
            char_data['description']['public'] = [{"description": desc_text}]
            print(f'[FIX] 修复了 description.public 格式')
        
        # 2. 移动玩家到走廊
        char_data['location'] = 'map-room-corridor-01'
        char_data['inventory'] = list(set(char_data.get('inventory', [])))  # 去重
        
        # 过滤掉无效的物品ID
        valid_items = ['item-book-01', 'item-key-01', 'item-lantern-01']
        char_data['inventory'] = [item for item in char_data['inventory'] if item in valid_items]
        
        cursor.execute('UPDATE characters SET data = ? WHERE id = ?',
                       (json.dumps(char_data, ensure_ascii=False), char_id))
        print(f'[MOVE] 玩家位置已更新到: map-room-corridor-01')
        print(f'[INVENTORY] 背包物品: {char_data["inventory"]}')
    
    # 3. 修复守卫角色 description.public 格式
    cursor.execute('SELECT id, data FROM characters WHERE id = ?', ('char-guard-01',))
    row = cursor.fetchone()
    if row:
        char_id, data = row
        char_data = json.loads(data)
        
        if isinstance(char_data.get('description', {}).get('public'), dict):
            desc_text = char_data['description']['public'].get('description', '')
            char_data['description']['public'] = [{"description": desc_text}]
            cursor.execute('UPDATE characters SET data = ? WHERE id = ?',
                           (json.dumps(char_data, ensure_ascii=False), char_id))
            print(f'[FIX] 修复了守卫 description.public 格式')
    
    # 4. 更新 game_state 的 current_scene_id
    cursor.execute('SELECT value FROM game_meta WHERE key = ?', ('game_state',))
    row = cursor.fetchone()
    if row:
        meta_data = json.loads(row[0])
        meta_data['current_scene_id'] = 'map-room-corridor-01'
        cursor.execute('UPDATE game_meta SET value = ? WHERE key = ?',
                       (json.dumps(meta_data, ensure_ascii=False), 'game_state'))
        print(f'[SCENE] 当前场景已更新到: map-room-corridor-01')
    
    conn.commit()
    conn.close()
    print('\n[OK] 所有更新已完成，玩家现在在走廊！')

if __name__ == '__main__':
    fix_and_move()
