"""AI модуль — Claude Sonnet + Vision + парсинг дій."""
import re
import asyncio
import json
import base64
import logging
from pathlib import Path
import anthropic
from core.config import ANTHROPIC_KEY, CLAUDE_MODEL, CLAUDE_MAX_TOKENS
from core.prompt import build_system
from core import memory
from core import kitchen
from core import token_tracker

log = logging.getLogger("core.ai")

client = anthropic.Anthropic(
    api_key=ANTHROPIC_KEY,
    max_retries=2,
    timeout=120.0
)

MAX_HISTORY_TOKENS = 4000
MAX_MSG_LEN = 3000


def _optimize_history(history: list) -> list:
    result, total = [], 0
    for msg in reversed(history):
        size = len(str(msg.get("content", ""))) // 4
        if total + size > MAX_HISTORY_TOKENS:
            break
        result.insert(0, msg)
        total += size
    if not result and history:
        result = history[-2:]
    return result


def _encode_image(image_path: str) -> tuple[str, str]:
    path = Path(image_path)
    try:
        from PIL import Image
        import io
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1568, 1568), Image.LANCZOS)
        buf = io.BytesIO()
        quality = 82
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        while buf.tell() > 1.5 * 1024 * 1024 and quality > 30:
            quality -= 15
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        log.info(f"Фото {path.name}: {buf.tell()/1024:.0f}KB якість {quality}")
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"
    except ImportError:
        raw = path.read_bytes()
        suffix = path.suffix.lower()
        media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                       ".png": "image/png", ".webp": "image/webp"}
        return base64.standard_b64encode(raw).decode("utf-8"), media_types.get(suffix, "image/jpeg")


def _parse_multi_actions(text: str) -> list[dict]:
    results = []
    for match in re.finditer(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL):
        try:
            results.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass
    return results


def _execute_action(action: dict):
    name = action.get("action")
    data = action.get("data", {})

    # ── Шоп-ліст ──────────────────────────────────────────────────────────────
    if name == "add_to_shopping":
        memory.add_to_shopping(data.get("items", []))
    elif name == "remove_from_shopping":
        memory.remove_from_shopping(data.get("items", []))
    elif name == "clear_shopping":
        memory.clear_shopping()

    # ── Інвентар ──────────────────────────────────────────────────────────────
    elif name == "update_inventory":
        memory.update_inventory(data.get("item", ""), data.get("status", "є"))

    # ── Морозилка ─────────────────────────────────────────────────────────────
    elif name == "add_to_freezer":
        memory.add_to_freezer(
            name=data.get("name", ""),
            location=data.get("location", ""),
            qty=data.get("qty"),
            unit=data.get("unit"),
        )
    elif name == "remove_from_freezer":
        memory.remove_from_freezer(data.get("name", ""), data.get("qty"))

    # ── Кулінарний мозок ──────────────────────────────────────────────────────
    elif name == "save_cooking_style":
        kitchen.add_cooking_style(data.get("tip", ""))
    elif name == "save_recipe":
        kitchen.add_recipe(
            name=data.get("name", ""),
            ingredients=data.get("ingredients", []),
            steps=data.get("steps", ""),
            tags=data.get("tags", []),
        )
    elif name == "remove_recipe":
        kitchen.remove_recipe(data.get("name", ""))

    elif name == "no_action":
        pass
    else:
        log.warning(f"Невідома дія: {name}")


def _clean_reply(text: str) -> str:
    return re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()



async def _summarize_session(user_id: int, history: list) -> str:
    """Стискає історію сесії в короткий summary."""
    history_text = "\n".join([
        f"{m['role'].upper()}: {str(m.get('content',''))[:300]}"
        for m in history[-20:]
    ])
    prompt = f"""Стисни цю розмову з домашнім асистентом Мег в summary до 400 символів.
Збережи: що просили зробити, що було додано/видалено зі списків, важливі деталі.
Викидай: привітання, підтвердження, зайві деталі.
Тільки факти, українською.

Розмова:
{history_text}

Summary:"""
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        log.error(f"summarize_session помилка: {e}")
        return ""

async def chat(user_id: int, user_message: str,
               image_paths: list = None, image_path: str = None) -> str:
    if image_path and not image_paths:
        image_paths = [image_path]
    image_paths = image_paths or []

    history = memory.get_session(user_id)

    # Превентивне стиснення до відправки в Claude
    if memory.needs_summary(user_id):
        log.info(f"[{user_id}] Сесія {len(history)} повідомлень — стискаємо перед запитом")
        summary = await _summarize_session(user_id, history)
        if summary:
            memory.save_session_with_summary(user_id, history, summary)
            history = memory.get_session(user_id)  # оновлена стиснута версія
            log.info(f"[{user_id}] Стиснуто: {len(history)} повідомлень")

    optimized = _optimize_history(history)

    content = []
    for i, path in enumerate(image_paths):
        try:
            data, media_type = _encode_image(path)
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data}
            })
            if len(image_paths) > 1:
                content.append({
                    "type": "text",
                    "text": f"[Фото {i+1} з {len(image_paths)}]"
                })
        except Exception as e:
            log.error(f"Помилка кодування фото {path}: {e}")

    if user_message and len(user_message) > MAX_MSG_LEN:
        user_message = user_message[:MAX_MSG_LEN] + "..."

    if image_paths and not user_message:
        user_message = f"Що бачиш на {'цих фото' if len(image_paths) > 1 else 'фото'}? Розпізнай і додай в інвентар."
    content.append({"type": "text", "text": user_message})

    optimized.append({"role": "user", "content": content})

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=build_system(),
            messages=optimized,
        )
        reply = response.content[0].text
        u = response.usage
        cache_read = getattr(u, 'cache_read_input_tokens', 0)
        cache_created = getattr(u, 'cache_creation_input_tokens', 0)
        log.info(
            f"[{user_id}] фото={len(image_paths)} "
            f"in={u.input_tokens} out={u.output_tokens} "
            f"cache_read={cache_read} "
            f"cache_created={cache_created}"
        )
        token_tracker.track(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read=cache_read,
            cache_created=cache_created,
            has_image=bool(image_paths),
        )
    except anthropic.APIError as e:
        log.error(f"Anthropic API: {e}")
        return "Сервіс тимчасово недоступний."
    except Exception as e:
        log.error(f"AI помилка: {e}")
        return "Технічна помилка. Спробуй ще раз."

    for action in _parse_multi_actions(reply):
        _execute_action(action)

    history_msg = f"{'[' + str(len(image_paths)) + ' фото] ' if image_paths else ''}{user_message}".strip()
    history.append({"role": "user", "content": history_msg})
    history.append({"role": "assistant", "content": reply})

    memory.save_session(user_id, history)
    return _clean_reply(reply)
