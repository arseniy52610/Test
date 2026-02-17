import json
import datetime
import os

PUNISHMENTS_FILE = "data/punishments.json"
NICKNAMES_FILE = "data/nicknames.json"

def load_punishments():
    try:
        with open(PUNISHMENTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_punishments(data):
    os.makedirs("data", exist_ok=True)
    with open(PUNISHMENTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def add_punishment(user_id, p_type, role_id, end_time=None, reason=""):
    data = load_punishments()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = []
    data[user_id].append({
        "type": p_type,
        "role_id": role_id,
        "end_time": end_time,
        "reason": reason,
        "issued_at": datetime.datetime.now(datetime.timezone.utc).timestamp()
    })
    save_punishments(data)

def remove_punishment(user_id, role_id):
    data = load_punishments()
    user_id = str(user_id)
    if user_id in data:
        data[user_id] = [p for p in data[user_id] if p["role_id"] != role_id]
        if not data[user_id]:
            del data[user_id]
        save_punishments(data)

def has_active_punishment(user_id, role_id):
    if not role_id:
        return False
    data = load_punishments()
    user_id = str(user_id)
    if user_id in data:
        for p in data[user_id]:
            if p["role_id"] == role_id:
                return True
    return False

def count_punishments(user_id, p_type=None):
    data = load_punishments()
    user_id = str(user_id)
    if user_id not in data:
        return 0
    if p_type:
        return sum(1 for p in data[user_id] if p["type"] == p_type)
    return len(data[user_id])

def load_nicknames():
    try:
        with open(NICKNAMES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def count_nicknames(user_id):
    data = load_nicknames()
    return len(data.get(str(user_id), []))