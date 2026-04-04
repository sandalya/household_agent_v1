"""AI модуль — Claude Sonnet + парсинг дій."""
import re
import json
import logging
import anthropic
from core.config import ANTHROPIC_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS
from core.prompt import build_system
from core import memory

log = logging.getLogger("core.ai")

client = anthropic.Anthropic(
    api_key=ANTHROPIC_KEY,
    max_retries=2,
    timeout=60.0
)

MAX_HISTORY_TOKENS = 6000


def _optimize_history(history: list) -> list:
    """Обрізає по токенах (1 токен ≈ 4 символи)."""
    result, total = [], 0
    for msg in reversed(history):
        size = len(str(msg.get("content", ""))) // 4
        if total + size > MAX_HISTORY_TOKENS:
            break
        result.insert(0, msg)
        total += size
    if not result and history:
        result = history[-2:]
    log.debug(f"History: {len(result)} повідомлень, ~{total} токенів")
    return result


def _parse_action(text: str) -> dict | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        log.warning("Не вдалось розпарсити action JSON")
        return None


def _execute_action(action: dict):
    name = action.get("action")
    data = action.get("data", {})
    if name == "add_to_shopping":
        memory.add_to_shopping(data.get("items", []))
    elif name == "remove_from_shopping":
        memory.remove_from_shopping(data.get("items", []))
    elif name == "clear_shopping":
        memory.clear_shopping()
    elif name == "update_inventory":
        memory.update_inventory(data.get("item", ""), data.get("status", "є"))
    elif name == "add_to_freezer":
        memory.add_to_freezer(
            name=data.get("name", ""),
            location=data.get("location", ""),
            qty=data.get("qty"),
            unit=data.get("unit"),
        )
    elif name == "remove_from_freezer":
        memory.remove_from_freezer(data.get("name", ""))
    elif name == "no_action":
        pass
    else:
        log.warning(f"Невідома дія: {name}")


def _clean_reply(text: str) -> str:
    """Прибираємо JSON-блок перед відправкою юзеру."""
    return re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()


async def chat(user_id: int, user_message: str) -> str:
    history = memory.get_session(user_id)
    optimized = _optimize_history(history)
    optimized.append({"role": "user", "content": user_message})

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=build_system(),
            messages=optimized,
        )
        reply = response.content[0].text
        u = response.usage
        log.info(
            f"[{user_id}] in={u.input_tokens} out={u.output_tokens} "
            f"cache_read={getattr(u,'cache_read_input_tokens',0)} "
            f"cache_created={getattr(u,'cache_creation_input_tokens',0)}"
        )
    except anthropic.APIError as e:
        log.error(f"Anthropic API: {e}")
        return "Сервіс тимчасово недоступний."
    except Exception as e:
        log.error(f"AI помилка: {e}")
        return "Технічна помилка. Спробуй ще раз."

    action = _parse_action(reply)
    if action:
        _execute_action(action)

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    memory.save_session(user_id, history)

    return _clean_reply(reply)
