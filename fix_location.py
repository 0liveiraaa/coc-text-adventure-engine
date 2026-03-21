import sqlite3
import json
import sys

# 连接数据库
conn = sqlite3.connect('data/game.db')
cursor = conn.cursor()

# 查看所有角色
cursor.execute('SELECT id FROM characters')
rows = cursor.fetchall()
print('数据库中的角色:', [r[0] for r in rows])

# 查找玩家角色（is_player=true）
player_id = None
for (char_id,) in rows:
    cursor.execute('SELECT data FROM characters WHERE id = ?', (char_id,))
    data = json.loads(cursor.fetchone()[0])
    if data.get('is_player'):
        player_id = char_id
        current_location = data.get('location', '未知')
        print(f'\n找到玩家: {char_id}')
        print(f'当前位置: {current_location}')
        print(f'名称: {data.get("name")}')
        break

if player_id:
    # 修改位置到走廊
    cursor.execute('SELECT data FROM characters WHERE id = ?', (player_id,))
    data = json.loads(cursor.fetchone()[0])
    data['location'] = 'map-room-corridor-01'
    
    cursor.execute('UPDATE characters SET data = ? WHERE id = ?',
                   (json.dumps(data, ensure_ascii=False), player_id))
    conn.commit()
    print(f'\n[OK] 位置已更新到: map-room-corridor-01')
else:
    print('未找到玩家角色')

conn.close()
