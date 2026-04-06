"""Трекер токенів і вартості для Household Agent (Мег)."""
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("core.token_tracker")

LOG_FILE = Path(__file__).parent.parent / "data" / "token_log.jsonl"

# Ціни в $ за 1 токен (claude-sonnet-4-5)
PRICES = {
    "input":          3.00 / 1_000_000,
    "output":        15.00 / 1_000_000,
    "cache_read":     0.30 / 1_000_000,
    "cache_creation": 3.75 / 1_000_000,
}


def _write_entry(entry: dict):
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log.error(f"token_tracker write: {e}")


def track(input_tokens: int, output_tokens: int,
          cache_read: int = 0, cache_created: int = 0,
          has_image: bool = False):
    cost = (
        input_tokens * PRICES["input"] +
        output_tokens * PRICES["output"] +
        cache_read * PRICES["cache_read"] +
        cache_created * PRICES["cache_creation"]
    )
    cost_without_cache = (
        (input_tokens + cache_read + cache_created) * PRICES["input"] +
        output_tokens * PRICES["output"]
    )
    saved = cost_without_cache - cost

    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "input": input_tokens,
        "output": output_tokens,
        "cache_read": cache_read,
        "cache_created": cache_created,
        "has_image": has_image,
        "cost": round(cost, 6),
        "saved": round(saved, 6),
    }
    threading.Thread(target=_write_entry, args=(entry,), daemon=True).start()
    return entry


def get_stats(days: int = 7) -> dict:
    if not LOG_FILE.exists():
        return {}

    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if datetime.fromisoformat(e["ts"]) >= cutoff:
                    entries.append(e)
            except Exception:
                continue

    if not entries:
        return {}

    total = len(entries)
    total_input    = sum(e.get("input", 0) for e in entries)
    total_output   = sum(e.get("output", 0) for e in entries)
    total_cache_r  = sum(e.get("cache_read", 0) for e in entries)
    total_cache_c  = sum(e.get("cache_created", 0) for e in entries)
    total_cost     = sum(e.get("cost", 0) for e in entries)
    total_saved    = sum(e.get("saved", 0) for e in entries)
    with_image     = sum(1 for e in entries if e.get("has_image"))

    cache_hit_rate = (
        total_cache_r / (total_input + total_cache_r) * 100
        if (total_input + total_cache_r) > 0 else 0
    )

    return {
        "days": days,
        "total_requests": total,
        "with_image": with_image,
        "total_input": total_input,
        "total_output": total_output,
        "total_cache_read": total_cache_r,
        "total_cache_created": total_cache_c,
        "cache_hit_rate": round(cache_hit_rate, 1),
        "total_cost": round(total_cost, 4),
        "total_saved": round(total_saved, 4),
        "avg_cost": round(total_cost / total, 5) if total else 0,
    }


def format_stats(days: int = 7) -> str:
    s = get_stats(days)
    if not s:
        return "📊 Даних поки немає — статистика накопичується з наступного запиту."

    return "\n".join([
        f"📊 Статистика Мег за {days} днів",
        f"Запитів: {s['total_requests']} (з фото: {s['with_image']})",
        "",
        f"🗃 Кеш: {s['cache_hit_rate']}% hit rate",
        f"   Зекономлено: ${s['total_saved']:.4f}",
        "",
        f"💰 Вартість:",
        f"   Всього: ${s['total_cost']:.4f}",
        f"   Середній запит: ${s['avg_cost']:.5f}",
        "",
        f"📈 Токени:",
        f"   Input: {s['total_input']:,}",
        f"   Output: {s['total_output']:,}",
        f"   Cache read: {s['total_cache_read']:,}",
    ])
