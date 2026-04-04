"""Персистентність через JSON файли."""
import json
import logging
from datetime import datetime
from core.config import DATA_DIR

log = logging.getLogger("core.memory")
DATA_DIR.mkdir(exist_ok=True)


def _load(filename: str, default):
    path = DATA_DIR / filename
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"Не вдалось прочитати {filename}: {e}")
        return default

def _save(filename: str, data):
    try:
        (DATA_DIR / filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        log.error(f"Не вдалось зберегти {filename}: {e}")


# ── Шоп-ліст ──────────────────────────────────────────────────────────────────

def get_shopping() -> list:
    return _load("shopping_list.json", [])

def add_to_shopping(items: list):
    current = get_shopping()
    lower = [i.lower() for i in current]
    for item in items:
        item = item.strip()
        if item and item.lower() not in lower:
            current.append(item)
            lower.append(item.lower())
    _save("shopping_list.json", current)

def remove_from_shopping(items: list):
    current = get_shopping()
    drop = [i.lower() for i in items]
    _save("shopping_list.json", [i for i in current if i.lower() not in drop])

def clear_shopping():
    _save("shopping_list.json", [])


# ── Інвентар ───────────────────────────────────────────────────────────────────

def get_inventory() -> dict:
    return _load("inventory.json", {})

def update_inventory(item: str, status: str):
    """status: є / мало / нема"""
    inv = get_inventory()
    inv[item.strip().lower()] = status
    _save("inventory.json", inv)


# ── Морозилка і пентрі ────────────────────────────────────────────────────────

def get_freezer() -> list:
    return _load("freezer.json", [])

def add_to_freezer(name: str, location: str, qty=None, unit=None):
    freezer = [i for i in get_freezer() if i["name"].lower() != name.strip().lower()]
    entry = {"name": name.strip(), "location": location.strip(),
             "added": datetime.now().strftime("%d.%m.%Y")}
    if qty is not None:
        entry["qty"] = qty
    if unit:
        entry["unit"] = unit
    freezer.append(entry)
    _save("freezer.json", freezer)

def remove_from_freezer(name: str):
    freezer = [i for i in get_freezer() if i["name"].lower() != name.strip().lower()]
    _save("freezer.json", freezer)


# ── Профілі сім'ї ─────────────────────────────────────────────────────────────

def get_family() -> dict:
    return _load("family.json", {})


# ── Сесія (history для Claude) ────────────────────────────────────────────────

def get_session(user_id: int) -> list:
    sessions = _load("sessions.json", {})
    return sessions.get(str(user_id), [])

def save_session(user_id: int, messages: list):
    sessions = _load("sessions.json", {})
    sessions[str(user_id)] = messages[-20:]
    _save("sessions.json", sessions)

def clear_session(user_id: int):
    sessions = _load("sessions.json", {})
    sessions[str(user_id)] = []
    _save("sessions.json", sessions)
