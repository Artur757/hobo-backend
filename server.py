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

# Временная база данных в памяти (в продакшене используйте PostgreSQL или SQLite)
# Структура: { user_id: { "name": str, "money": float, "rankIdx": int, "referrer_id": int, "ref_bonus": float } }
db = {}

class SyncData(BaseModel):
    user_id: int
    name: str
    money: float
    rankIdx: int
    referrer_id: int = None
    delta_earned: float = 0.0 # Сколько заработано с прошлого синка

@app.post("/api/sync")
def sync_player(data: SyncData):
    # Если игрок новый
    if data.user_id not in db:
        db[data.user_id] = {
            "name": data.name, "money": data.money, 
            "rankIdx": data.rankIdx, "referrer_id": data.referrer_id, "ref_bonus": 0
        }
    else:
        # Обновляем данные
        db[data.user_id]["money"] = data.money
        db[data.user_id]["rankIdx"] = data.rankIdx
        db[data.user_id]["name"] = data.name

    # Начисляем 10% рефоводу, если он есть и был заработок
    ref_id = db[data.user_id].get("referrer_id")
    if ref_id and ref_id in db and data.delta_earned > 0:
        db[ref_id]["ref_bonus"] += data.delta_earned * 0.10

    return {"status": "ok", "ref_bonus_available": db[data.user_id].get("ref_bonus", 0)}

@app.post("/api/claim_ref")
def claim_ref(user_id: int):
    if user_id in db and db[user_id]["ref_bonus"] > 0:
        bonus = db[user_id]["ref_bonus"]
        db[user_id]["money"] += bonus
        db[user_id]["ref_bonus"] = 0
        return {"claimed": bonus}
    return {"claimed": 0}

@app.post("/api/raid")
def raid_player(attacker_id: int):
    if attacker_id not in db:
        raise HTTPException(400, "Attacker not found")
    
    attacker = db[attacker_id]
    
    # Ищем всех игроков ТАКОГО ЖЕ РАНГА, кроме самого себя, у которых есть деньги
    targets = [uid for uid, p in db.items() if p["rankIdx"] == attacker["rankIdx"] and uid != attacker_id and p["money"] > 100]
    
    if not targets:
        return {"success": False, "message": "На районе нет равных фрайеров для набега."}

    # Выбираем случайную жертву
    target_id = random.choice(targets)
    target = db[target_id]

    # Шанс победы 50/50
    is_win = random.choice([True, False])
    
    if is_win:
        # Крадем от 5% до 15% кассы жертвы
        loot_percent = random.uniform(0.05, 0.15)
        loot = int(target["money"] * loot_percent)
        target["money"] -= loot
        attacker["money"] += loot
        return {"success": True, "is_win": True, "target_name": target["name"], "loot": loot, "message": f"Вы успешно прессанули {target['name']} и отжали {loot} ₽!"}
    else:
        # Штраф при поражении (например, теряем 5% своей кассы)
        penalty = int(attacker["money"] * 0.05)
        attacker["money"] -= penalty
        return {"success": True, "is_win": False, "target_name": target["name"], "loot": -penalty, "message": f"{target['name']} дал отпор! Вы потеряли {penalty} ₽, убегая."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
