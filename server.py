import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random

app = FastAPI(title="Hobo Empire API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация SQLite базы данных
def init_db():
    conn = sqlite3.connect("hobo_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            money REAL,
            rankIdx INTEGER,
            referrer_id INTEGER,
            ref_bonus REAL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect("hobo_database.db")
    conn.row_factory = sqlite3.Row # Позволяет обращаться к колонкам по имени
    return conn

class SyncData(BaseModel):
    user_id: int
    name: str
    money: float
    rankIdx: int
    referrer_id: int = None
    delta_earned: float = 0.0

@app.post("/api/sync")
def sync_player(data: SyncData):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Сохраняем или обновляем игрока в базе
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (data.user_id,))
    player = cursor.fetchone()
    
    if not player:
        cursor.execute('''
            INSERT INTO players (user_id, name, money, rankIdx, referrer_id, ref_bonus)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (data.user_id, data.name, data.money, data.rankIdx, data.referrer_id))
    else:
        # Обновляем только если у игрока стало больше денег (защита от потери при перезапуске клиента)
        if data.money > player["money"] or data.rankIdx > player["rankIdx"]:
            cursor.execute('''
                UPDATE players SET name = ?, money = ?, rankIdx = ? WHERE user_id = ?
            ''', (data.name, data.money, data.rankIdx, data.user_id))
        
    # Начисляем 10% рефоводу
    if data.referrer_id and data.delta_earned > 0:
        cursor.execute('''
            UPDATE players SET ref_bonus = ref_bonus + ? WHERE user_id = ?
        ''', (data.delta_earned * 0.10, data.referrer_id))
        
    conn.commit()
    
    # Получаем актуальный бонус для ответа
    cursor.execute("SELECT ref_bonus FROM players WHERE user_id = ?", (data.user_id,))
    current_bonus = cursor.fetchone()["ref_bonus"]
    conn.close()
    
    return {"status": "ok", "ref_bonus_available": current_bonus}

@app.post("/api/claim_ref")
def claim_ref(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ref_bonus, money FROM players WHERE user_id = ?", (user_id,))
    player = cursor.fetchone()
    
    claimed = 0
    if player and player["ref_bonus"] > 0:
        claimed = player["ref_bonus"]
        new_money = player["money"] + claimed
        cursor.execute("UPDATE players SET money = ?, ref_bonus = 0 WHERE user_id = ?", (new_money, user_id))
        conn.commit()
        
    conn.close()
    return {"claimed": claimed}

@app.post("/api/raid")
def raid_player(attacker_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (attacker_id,))
    attacker = cursor.fetchone()
    
    if not attacker:
        conn.close()
        raise HTTPException(400, "Attacker not found")
        
    # Ищем всех игроков ТАКОГО ЖЕ РАНГА с деньгами
    cursor.execute("SELECT * FROM players WHERE rankIdx = ? AND user_id != ? AND money > 100", (attacker["rankIdx"], attacker_id))
    targets = cursor.fetchall()
    
    if not targets:
        conn.close()
        return {"success": False, "message": "На районе нет равных фрайеров для набега."}
        
    target = random.choice(targets)
    is_win = random.choice([True, False])
    
    if is_win:
        loot = int(target["money"] * random.uniform(0.05, 0.15))
        cursor.execute("UPDATE players SET money = money - ? WHERE user_id = ?", (loot, target["user_id"]))
        cursor.execute("UPDATE players SET money = money + ? WHERE user_id = ?", (loot, attacker_id))
        conn.commit()
        conn.close()
        return {"success": True, "is_win": True, "target_name": target["name"], "loot": loot, "message": f"Вы успешно прессанули {target['name']} и отжали {loot} ₽!"}
    else:
        penalty = int(attacker["money"] * 0.05)
        cursor.execute("UPDATE players SET money = money - ? WHERE user_id = ?", (penalty, attacker_id))
        conn.commit()
        conn.close()
        return {"success": True, "is_win": False, "target_name": target["name"], "loot": -penalty, "message": f"{target['name']} дал отпор! Вы потеряли {penalty} ₽."}

# НОВЫЙ ЭНДПОИНТ: ГЛОБАЛЬНЫЙ ЛИДЕРБОРД
@app.get("/api/leaderboard")
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем ТОП-100 богачей
    cursor.execute("SELECT user_id, name, money, rankIdx FROM players ORDER BY money DESC LIMIT 100")
    top_players = cursor.fetchall()
    conn.close()
    
    leaders = []
    for p in top_players:
        leaders.append({
            "id": p["user_id"],
            "name": p["name"],
            "money": p["money"],
            "rankIdx": p["rankIdx"]
        })
        
    return {"leaders": leaders}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
