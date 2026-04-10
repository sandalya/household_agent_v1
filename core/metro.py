import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path

log = logging.getLogger('core.metro')


class MetroUnavailableError(Exception):
    pass

BASE_DIR = Path(__file__).parent.parent
METRO_CONFIG_FILE = BASE_DIR / 'data' / 'metro_config.json'

# Магазини Metro Київ
KYIV_STORES = {
    "poznyaky": {"id": "48215610", "name": "Metro Позняки"},
    "teremky":  {"id": "48215611", "name": "Metro Теремки"},
    "troyeschyna": {"id": "48215633", "name": "Metro Троєщина"},
}

DEFAULT_STORE = "poznyaky"
API_BASE = "https://stores-api.zakaz.ua/stores"


def _load_config() -> dict:
    if METRO_CONFIG_FILE.exists():
        return json.loads(METRO_CONFIG_FILE.read_text(encoding='utf-8'))
    return {"store_key": DEFAULT_STORE}


def _save_config(cfg: dict):
    METRO_CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def get_store() -> dict:
    cfg = _load_config()
    key = cfg.get("store_key", DEFAULT_STORE)
    return KYIV_STORES.get(key, KYIV_STORES[DEFAULT_STORE])


def set_store(key: str) -> bool:
    if key not in KYIV_STORES:
        return False
    cfg = _load_config()
    cfg["store_key"] = key
    _save_config(cfg)
    return True


def search_product(query: str, store_id: str = None, per_page: int = 3) -> list[dict]:
    """Пошук товару. Повертає список варіантів."""
    if not store_id:
        store_id = get_store()["id"]
    q = urllib.parse.quote(query)
    url = f"{API_BASE}/{store_id}/products/search/?per_page={per_page}&q={q}"
    req = urllib.request.Request(url, headers={
        "Accept-Language": "uk",
        "User-Agent": "Mozilla/5.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        log.error(f"Metro API error for \'{query}\': {e}")
        if e.code in (503, 502, 504):
            raise MetroUnavailableError(f"Metro API недоступний (HTTP {e.code})")
        return []
    except Exception as e:
        log.error(f"Metro API error for \'{query}\': {e}")
        return []

    results = []
    for item in data.get("results", []):
        if not item.get("in_stock"):
            continue
        price_raw = item.get("price", 0)
        old_price_raw = item.get("discount", {}).get("old_price", price_raw)
        discount = item.get("discount", {})
        results.append({
            "title": item.get("title", ""),
            "price": round(price_raw / 100, 2),
            "old_price": round(old_price_raw / 100, 2) if discount.get("status") else None,
            "discount_pct": discount.get("value", 0) if discount.get("status") else 0,
            "ean": item.get("ean", ""),
            "sku": item.get("sku", ""),
            "url": item.get("web_url", ""),
            "unit": item.get("unit", "pcs"),
            "in_stock": item.get("in_stock", False),
        })
    return results



import re as _re

def _parse_quantity(item_text: str, unit: str) -> tuple[str, float]:
    """
    Витягує кількість з тексту товару.
    Повертає (clean_query, amount).
    """
    text = item_text.strip()

    # Шукаємо патерни: "14 шт", "6шт", "1.4кг", "50г", "210мл"
    patterns = [
        (r"(\d+(?:[.,]\d+)?)\s*кг", "kg"),
        (r"(\d+(?:[.,]\d+)?)\s*г\b", "g"),
        (r"(\d+(?:[.,]\d+)?)\s*мл\b", "ml"),
        (r"(\d+(?:[.,]\d+)?)\s*шт\b", "pcs"),
        (r"(\d+(?:[.,]\d+)?)\s*пучок", "pcs"),
        (r"(\d+(?:[.,]\d+)?)\s*зубчик", "pcs"),
    ]

    amount = 1.0
    clean = text

    for pattern, qty_unit in patterns:
        m = _re.search(pattern, text, _re.IGNORECASE)
        if m:
            val = float(m.group(1).replace(",", "."))
            # Конвертуємо в одиниці API
            if unit == "kg":
                if qty_unit == "g":
                    amount = round(val / 1000, 3)
                elif qty_unit == "kg":
                    amount = val
                else:  # шт — просто кількість
                    amount = val
            else:
                # pcs товар
                if qty_unit in ("g", "ml"):
                    amount = 1  # не конвертуємо, беремо 1 упаковку
                else:
                    amount = int(val)

            # Прибираємо кількість з пошукового запиту
            clean = _re.sub(r"\s*" + pattern, "", text, flags=_re.IGNORECASE).strip()
            # Прибираємо залишки в дужках
            clean = _re.sub(r"\s*\(.*?\)", "", clean).strip()
            break

    # Мінімум 1
    if amount < 0.001:
        amount = 1

    return clean, amount


def build_order_from_shopping_list(shopping_list: list[str], store_id: str = None, ean_index: dict = None) -> dict:
    """
    Для кожного товару зі списку шукає найкращий варіант в Metro.
    Спочатку шукає в ean_index (списки заказ.юа), потім через пошук+Claude.
    Повертає:
      found: [{item, product, price, url}]
      not_found: [item]
      total: float
    """
    import re as _re2
    found = []
    not_found = []

    for item in shopping_list:
        search_query = _re2.sub(r"\s*\(.*?\)", "", item).strip()
        best = None

        # Спочатку шукаємо в списках заказ.юа по ean
        if ean_index:
            for ean in ean_index:
                candidates = search_product(ean, store_id=store_id, per_page=1)
                if candidates:
                    c = candidates[0]
                    title_lower = c["title"].lower()
                    query_lower = search_query.lower().split()[0]
                    if query_lower in title_lower:
                        best = c
                        best["amount"] = 1
                        log.info(f"list match: {item} -> {c['title']} (ean={ean})")
                        break

        # Якщо не знайшли в списках — шукаємо через пошук+Claude
        if not best:
            candidates = search_product(search_query, store_id=store_id, per_page=5)
            best = pick_best_product(item, candidates)

        if best:
            found.append({
                "item": item,
                "product": best["title"],
                "price": best["price"],
                "old_price": best.get("old_price"),
                "discount_pct": best.get("discount_pct", 0),
                "url": best["url"],
                "ean": best["ean"],
                "amount": best.get("amount", 1),
                "unit": best["unit"],
            })
        else:
            not_found.append(item)

    total = sum(p["price"] for p in found)
    return {"found": found, "not_found": not_found, "total": round(total, 2)}


def format_order_message(order: dict, store_name: str = None) -> str:
    """Форматує повідомлення для підтвердження замовлення."""
    if not store_name:
        store_name = get_store()["name"]

    lines = [f"🛒 *Замовлення в {store_name}*\n"]

    for p in order["found"]:
        price_str = f"{p['price']:.0f} грн"
        if p.get("discount_pct"):
            price_str += f" ~~{p['old_price']:.0f}~~ (-{p['discount_pct']}%)"
        lines.append(f"✅ {p['item']}\n   [{p['product']}]({p['url']})\n   {price_str}")

    if order["not_found"]:
        lines.append("\n❌ *Не знайдено:*")
        for item in order["not_found"]:
            lines.append(f"   • {item}")

    lines.append(f"\n💰 *Разом: {order['total']:.0f} грн*")
    lines.append(f"\n🏪 [{store_name}](https://metro.zakaz.ua/uk/)")

    return "\n".join(lines)


# ── CART ──────────────────────────────────────────────────────────────────────

CART_BASE = "https://stores-api.zakaz.ua/cart"

def _cart_headers(token: str) -> dict:
    return {
        "Accept": "application/json",
        "Accept-Language": "uk",
        "Content-Type": "application/json",
        "Origin": "https://metro.zakaz.ua",
        "Referer": "https://metro.zakaz.ua/",
        "User-Agent": "Mozilla/5.0",
        "X-Chain": "metro",
        "Cookie": f"__Host-zakaz-sid={token}",
    }


KNOWN_USERS = {
    189793675: "sashok",
    255525: "ksu",
}

def save_token(token: str, user_id: int = None):
    cfg = _load_config()
    cfg["token"] = token
    if user_id and user_id in KNOWN_USERS:
        nick = KNOWN_USERS[user_id]
        cfg.setdefault("users", {})[nick] = {"token": token, "user_id": user_id}
        cfg["active_user"] = nick
        log.info(f"save_token: збережено для {nick}")
    _save_config(cfg)


def load_token() -> str | None:
    cfg = _load_config()
    active = cfg.get("active_user")
    if active:
        users = cfg.get("users", {})
        if active in users:
            return users[active].get("token")
    return cfg.get("token")


def switch_user(nick: str) -> bool:
    cfg = _load_config()
    users = cfg.get("users", {})
    if nick not in users:
        return False
    cfg["active_user"] = nick
    cfg["token"] = users[nick]["token"]
    _save_config(cfg)
    log.info(f"switch_user: активний юзер -> {nick}")
    return True


def get_active_user() -> str | None:
    return _load_config().get("active_user")


def get_saved_users() -> dict:
    return _load_config().get("users", {})

def get_cart(token: str) -> dict | None:
    req = urllib.request.Request(
        f"{CART_BASE}/",
        headers=_cart_headers(token)
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log.error(f"get_cart error: {e}")
        return None


def clear_cart(token: str) -> bool:
    """Очищає кошик перед заповненням."""
    cart = get_cart(token)
    if not cart:
        return False
    items = cart.get("items", [])
    if not items:
        return True
    # Видаляємо кожен товар
    payload = json.dumps({
        "items": [{"ean": i["ean"], "amount": 0, "operation": "set"} for i in items]
    }).encode('utf-8')
    req = urllib.request.Request(
        f"{CART_BASE}/items/",
        data=payload,
        headers=_cart_headers(token),
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        log.error(f"clear_cart error: {e}")
        return False


def add_to_cart(token: str, items: list[dict]) -> bool:
    """
    items: [{"ean": "...", "amount": 1}]
    """
    payload = json.dumps({
        "items": [{"ean": i["ean"], "amount": i.get("amount", 1), "operation": "add"} for i in items]
    }).encode('utf-8')
    req = urllib.request.Request(
        f"{CART_BASE}/items/",
        data=payload,
        headers=_cart_headers(token),
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        log.error(f"add_to_cart error: {e}")
        return False


def fill_cart_from_order(token: str, order: dict) -> dict:
    """
    Заповнює кошик з результату build_order_from_shopping_list.
    Спочатку очищає кошик, потім додає товари.
    Повертає: {added: int, skipped: int}
    """
    items_to_add = [{"ean": p["ean"], "amount": p.get("amount", 1)} for p in order["found"] if p.get("ean")]
    if not items_to_add:
        return {"added": 0, "skipped": len(order["found"])}
    # Очищаємо кошик перед заповненням
    clear_cart(token)
    ok = add_to_cart(token, items_to_add)
    return {
        "added": len(items_to_add) if ok else 0,
        "skipped": 0 if ok else len(items_to_add)
    }


def pick_best_product(item_query: str, candidates: list[dict]) -> dict | None:
    """
    Використовує Claude щоб вибрати найкращий товар зі списку кандидатів.
    Повертає вибраний продукт з правильним amount.
    """
    import sys as _sys
    _sys.path.insert(0, '/home/sashok/.openclaw/workspace/household_agent/venv/lib/python3.11/site-packages')
    import anthropic
    import json as _json
    from core.config import ANTHROPIC_KEY as ANTHROPIC_API_KEY

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    candidates_text = "\n".join([
        f"{i+1}. {c['title']} | {c['price']} грн | unit={c['unit']}"
        for i, c in enumerate(candidates)
    ])

    prompt = f"""Покупець хоче купити: "{item_query}"

Доступні варіанти в Metro:
{candidates_text}

Вибери НАЙКРАЩИЙ варіант. Правила:
- Назва має точно відповідати запиту (ігноруй нерелевантне — наприклад рисове борошно це не рис)
- Якщо запит "рис 1кг" — шукай саме рис крупу, не борошно і не локшину
- Для вагових товарів (unit=kg): якщо запит "морква 6 шт" — amount=0.6 (приблизно 100г на штуку)
- Для штучних товарів в упаковках: якщо треба 14шт а упаковка 18шт — amount=1 (одна упаковка)
- Якщо жоден варіант не підходить за змістом — поверни index=0

Відповідай ТІЛЬКИ JSON (без пояснень):
{{"index": 1, "amount": 1, "reason": "коротко чому"}}

де index — номер товару (1-{len(candidates)}), або 0 якщо нічого не підходить.
amount — скільки одиниць/кг купити."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        # Прибираємо можливі ```json
        text = text.replace("```json", "").replace("```", "").strip()
        data = _json.loads(text)
        idx = data.get("index", 0)
        amount = data.get("amount", 1)
        reason = data.get("reason", "")
        if idx == 0 or idx > len(candidates):
            return None
        result = dict(candidates[idx - 1])
        result["amount"] = amount
        log.info(f"pick_best '{item_query}' → #{idx} {result['title'][:30]} x{amount} ({reason})")
        return result
    except Exception as e:
        log.error(f"pick_best error: {e}")
        return candidates[0]


# ── ORDERS ANALYSIS ───────────────────────────────────────────────────────────

PATTERNS_FILE = BASE_DIR / 'data' / 'purchase_patterns.json'
USER_API_BASE = "https://stores-api.zakaz.ua/user"



LISTS_FILE = BASE_DIR / 'data' / 'zakaz_lists.json'


def get_lists(token: str) -> list[dict] | None:
    """Завантажує списки користувача з заказ.юа."""
    url = f"{USER_API_BASE}/lists"
    req = urllib.request.Request(url, headers=_cart_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        LISTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        log.info(f"get_lists: завантажено {len(data)} списків")
        return data
    except Exception as e:
        log.error(f"get_lists error: {e}")
        return None


def build_ean_index(lists: list[dict]) -> dict[str, str]:
    """Будує індекс ean -> list_name для швидкого пошуку."""
    index = {}
    for lst in lists:
        for item in lst.get('items', []):
            ean = item.get('ean', '')
            if ean:
                index[ean] = lst.get('name', '')
    return index

def get_all_orders(token: str) -> list[dict]:
    """Завантажує всі замовлення з усіх сторінок."""
    all_orders = []
    page = 1
    while True:
        url = f"{USER_API_BASE}/orders/?page={page}&per_page=10&items_count=10"
        req = urllib.request.Request(url, headers=_cart_headers(token))
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            log.error(f"get_all_orders page={page} error: {e}")
            break
        if not data:
            break
        all_orders.extend(data)
        if len(data) < 10:
            break
        page += 1
    log.info(f"get_all_orders: завантажено {len(all_orders)} замовлень")
    return all_orders


def analyze_purchase_patterns(orders: list[dict]) -> dict:
    """
    Аналізує замовлення і повертає патерни закупок.
    Зберігає результат в data/purchase_patterns.json
    """
    from collections import defaultdict

    product_stats = defaultdict(lambda: {
        "title": "",
        "ean": "",
        "order_count": 0,
        "total_amount": 0.0,
        "avg_amount": 0.0,
        "unit": "pcs",
        "avg_price": 0.0,
        "orders": [],
    })

    total_orders = len(orders)

    for order in orders:
        order_id = order.get("id", "")
        order_date = order.get("created", "")
        for item in order.get("items", []):
            ean = item.get("ean", "")
            if not ean:
                continue
            s = product_stats[ean]
            s["title"] = item.get("title", "")
            s["ean"] = ean
            s["unit"] = item.get("unit", "pcs")
            s["order_count"] += 1
            amount = item.get("amount", 1)
            if s["unit"] == "kg":
                amount = round(amount / 1000, 2)
            s["total_amount"] += amount
            s["avg_price"] = round(item.get("price", 0) / 100, 2)
            s["orders"].append({"id": order_id, "date": order_date, "amount": amount})

    # Рахуємо середню кількість і частоту
    results = []
    for ean, s in product_stats.items():
        s["avg_amount"] = round(s["total_amount"] / s["order_count"], 2)
        s["frequency_pct"] = round(s["order_count"] / total_orders * 100)
        results.append(s)

    # Сортуємо по частоті
    results.sort(key=lambda x: x["order_count"], reverse=True)

    patterns = {
        "total_orders": total_orders,
        "analyzed_at": __import__('datetime').datetime.now().strftime("%d.%m.%Y %H:%M"),
        "products": results,
    }

    PATTERNS_FILE.write_text(
        json.dumps(patterns, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    log.info(f"analyze_purchase_patterns: {len(results)} унікальних товарів збережено")
    return patterns


def format_patterns_message(patterns: dict) -> str:
    """Форматує результат аналізу для Telegram."""
    total = patterns["total_orders"]
    products = patterns["products"]
    date = patterns.get("analyzed_at", "")

    lines = [f"📊 *Аналіз закупок Metro*", f"_Замовлень проаналізовано: {total} | {date}_\n"]

    # Регулярні (100% замовлень)
    always = [p for p in products if p["order_count"] == total]
    if always:
        lines.append("🔁 *Беремо завжди:*")
        for p in always:
            lines.append(f"  • {p['title']} — {p['avg_amount']} {p['unit']} щоразу")

    # Часто (більше 50%)
    often = [p for p in products if 0 < p["order_count"] < total and p["frequency_pct"] >= 50]
    if often:
        lines.append("\n📌 *Часто беремо:*")
        for p in often:
            lines.append(f"  • {p['title']} — {p['frequency_pct']}% замовлень")

    # Рідко
    rare = [p for p in products if p["frequency_pct"] < 50]
    if rare:
        lines.append(f"\n🔸 *Рідше:* {len(rare)} товарів")

    lines.append(f"\n_Всього унікальних товарів: {len(products)}_")
    return "\n".join(lines)


# ── ORDERS ANALYSIS ───────────────────────────────────────────────────────────

PATTERNS_FILE = BASE_DIR / 'data' / 'purchase_patterns.json'
USER_API_BASE = "https://stores-api.zakaz.ua/user"



LISTS_FILE = BASE_DIR / 'data' / 'zakaz_lists.json'


def get_lists(token: str) -> list[dict] | None:
    """Завантажує списки користувача з заказ.юа."""
    url = f"{USER_API_BASE}/lists"
    req = urllib.request.Request(url, headers=_cart_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        LISTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        log.info(f"get_lists: завантажено {len(data)} списків")
        return data
    except Exception as e:
        log.error(f"get_lists error: {e}")
        return None


def build_ean_index(lists: list[dict]) -> dict[str, str]:
    """Будує індекс ean -> list_name для швидкого пошуку."""
    index = {}
    for lst in lists:
        for item in lst.get('items', []):
            ean = item.get('ean', '')
            if ean:
                index[ean] = lst.get('name', '')
    return index

def get_all_orders(token: str) -> list[dict]:
    """Завантажує всі замовлення з усіх сторінок."""
    all_orders = []
    page = 1
    while True:
        url = f"{USER_API_BASE}/orders/?page={page}&per_page=10&items_count=10"
        req = urllib.request.Request(url, headers=_cart_headers(token))
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            log.error(f"get_all_orders page={page} error: {e}")
            break
        if not data:
            break
        all_orders.extend(data)
        if len(data) < 10:
            break
        page += 1
    log.info(f"get_all_orders: завантажено {len(all_orders)} замовлень")
    return all_orders


def analyze_purchase_patterns(orders: list[dict]) -> dict:
    """
    Аналізує замовлення і повертає патерни закупок.
    Зберігає результат в data/purchase_patterns.json
    """
    from collections import defaultdict

    product_stats = defaultdict(lambda: {
        "title": "",
        "ean": "",
        "order_count": 0,
        "total_amount": 0.0,
        "avg_amount": 0.0,
        "unit": "pcs",
        "avg_price": 0.0,
        "orders": [],
    })

    total_orders = len(orders)

    for order in orders:
        order_id = order.get("id", "")
        order_date = order.get("created", "")
        for item in order.get("items", []):
            ean = item.get("ean", "")
            if not ean:
                continue
            s = product_stats[ean]
            s["title"] = item.get("title", "")
            s["ean"] = ean
            s["unit"] = item.get("unit", "pcs")
            s["order_count"] += 1
            amount = item.get("amount", 1)
            if s["unit"] == "kg":
                amount = round(amount / 1000, 2)
            s["total_amount"] += amount
            s["avg_price"] = round(item.get("price", 0) / 100, 2)
            s["orders"].append({"id": order_id, "date": order_date, "amount": amount})

    # Рахуємо середню кількість і частоту
    results = []
    for ean, s in product_stats.items():
        s["avg_amount"] = round(s["total_amount"] / s["order_count"], 2)
        s["frequency_pct"] = round(s["order_count"] / total_orders * 100)
        results.append(s)

    # Сортуємо по частоті
    results.sort(key=lambda x: x["order_count"], reverse=True)

    patterns = {
        "total_orders": total_orders,
        "analyzed_at": __import__('datetime').datetime.now().strftime("%d.%m.%Y %H:%M"),
        "products": results,
    }

    PATTERNS_FILE.write_text(
        json.dumps(patterns, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    log.info(f"analyze_purchase_patterns: {len(results)} унікальних товарів збережено")
    return patterns


def format_patterns_message(patterns: dict) -> str:
    """Форматує результат аналізу для Telegram."""
    total = patterns["total_orders"]
    products = patterns["products"]
    date = patterns.get("analyzed_at", "")

    lines = [f"📊 *Аналіз закупок Metro*", f"_Замовлень проаналізовано: {total} | {date}_\n"]

    # Регулярні (100% замовлень)
    always = [p for p in products if p["order_count"] == total]
    if always:
        lines.append("🔁 *Беремо завжди:*")
        for p in always:
            lines.append(f"  • {p['title']} — {p['avg_amount']} {p['unit']} щоразу")

    # Часто (більше 50%)
    often = [p for p in products if 0 < p["order_count"] < total and p["frequency_pct"] >= 50]
    if often:
        lines.append("\n📌 *Часто беремо:*")
        for p in often:
            lines.append(f"  • {p['title']} — {p['frequency_pct']}% замовлень")

    # Рідко
    rare = [p for p in products if p["frequency_pct"] < 50]
    if rare:
        lines.append(f"\n🔸 *Рідше:* {len(rare)} товарів")

    lines.append(f"\n_Всього унікальних товарів: {len(products)}_")
    return "\n".join(lines)


def suggest_missing_items(shopping_list: list, inventory: dict, top_n: int = 30, min_orders: int = 8) -> list[dict]:
    """
    Порівнює шоп-ліст і інвентар з purchase_patterns.
    Повертає список товарів які варто додати (регулярні але відсутні).
    """
    if not PATTERNS_FILE.exists():
        return []

    patterns = json.loads(PATTERNS_FILE.read_text(encoding='utf-8'))
    products = patterns.get("products", [])

    # Нормалізуємо шоп-ліст і інвентар для порівняння
    shopping_lower = set(i.lower() for i in shopping_list)
    inventory_present = set(k.lower() for k, v in inventory.items() if v in ("є", "мало"))

    suggestions = []
    for p in products[:top_n * 3]:  # беремо з запасом бо будемо фільтрувати
        if p["order_count"] < min_orders:
            break
        title = p["title"]
        title_lower = title.lower()

        # Перевіряємо чи є вже в шоп-листі (по першому слову)
        first_word = title_lower.split()[0]
        in_shopping = any(first_word in s for s in shopping_lower)
        if in_shopping:
            continue

        # Перевіряємо інвентар
        in_inventory = any(first_word in k for k in inventory_present)
        if in_inventory:
            continue

        suggestions.append({
            "title": title,
            "ean": p["ean"],
            "order_count": p["order_count"],
            "avg_amount": p["avg_amount"],
            "unit": p["unit"],
            "frequency_pct": p["frequency_pct"],
        })

        if len(suggestions) >= top_n:
            break

    return suggestions


def suggest_missing_items(shopping_list: list, inventory: dict, top_n: int = 30, min_orders: int = 8) -> list[dict]:
    if not PATTERNS_FILE.exists():
        return []
    patterns = json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
    products = patterns.get("products", [])
    shopping_lower = set(i.lower() for i in shopping_list)
    inventory_present = set(k.lower() for k, v in inventory.items() if v in ("є", "мало"))
    suggestions = []
    for p in products:
        if p["order_count"] < min_orders:
            break
        title = p["title"]
        title_lower = title.lower()
        first_word = title_lower.split()[0]
        in_shopping = any(first_word in s for s in shopping_lower)
        if in_shopping:
            continue
        in_inventory = any(first_word in k for k in inventory_present)
        if in_inventory:
            continue
        suggestions.append({"title": title, "ean": p["ean"], "order_count": p["order_count"], "avg_amount": p["avg_amount"], "unit": p["unit"], "frequency_pct": p["frequency_pct"]})
        if len(suggestions) >= top_n:
            break
    return suggestions

