"""AI модуль — Claude Sonnet + Vision + tool use."""
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

# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "add_to_shopping",
        "description": "Додає один або кілька товарів до списку покупок",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Список товарів, наприклад: [\"молоко\", \"яйця 10шт\"]"
                }
            },
            "required": ["items"]
        }
    },
    {
        "name": "remove_from_shopping",
        "description": "Видаляє один або кілька товарів зі списку покупок",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Список товарів для видалення"
                }
            },
            "required": ["items"]
        }
    },
    {
        "name": "clear_shopping",
        "description": "Повністю очищає список покупок",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "update_inventory",
        "description": "Оновлює статус товару в інвентарі (є / мало / нема)",
        "input_schema": {
            "type": "object",
            "properties": {
                "item":   {"type": "string", "description": "Назва товару"},
                "status": {"type": "string", "enum": ["є", "мало", "нема"], "description": "Статус"}
            },
            "required": ["item", "status"]
        }
    },
    {
        "name": "add_to_freezer",
        "description": "Додає продукт до морозилки",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":     {"type": "string", "description": "Назва продукту"},
                "location": {"type": "string", "description": "Місце (верхня/середня/нижня полиця)"},
                "qty":      {"type": "number", "description": "Кількість (необов'язково)"},
                "unit":     {"type": "string", "description": "Одиниця виміру (необов'язково)"}
            },
            "required": ["name", "location"]
        }
    },
    {
        "name": "remove_from_freezer",
        "description": "Видаляє або зменшує кількість продукту в морозилці",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Назва продукту"},
                "qty":  {"type": "number", "description": "Кількість для зменшення (необов'язково)"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "save_cooking_style",
        "description": "Зберігає кулінарну пораду або стильову замітку",
        "input_schema": {
            "type": "object",
            "properties": {
                "tip": {"type": "string", "description": "Текст поради"}
            },
            "required": ["tip"]
        }
    },
    {
        "name": "save_recipe",
        "description": "Зберігає рецепт",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":        {"type": "string", "description": "Назва страви"},
                "ingredients": {"type": "array", "items": {"type": "string"}, "description": "Список інгредієнтів"},
                "steps":       {"type": "string", "description": "Кроки приготування"},
                "tags":        {"type": "array", "items": {"type": "string"}, "description": "Теги"}
            },
            "required": ["name", "ingredients", "steps"]
        }
    },
    {
        "name": "remove_recipe",
        "description": "Видаляє рецепт за назвою",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Назва рецепту"}
            },
            "required": ["name"]
        }
    },
]

# ── Tool executor ──────────────────────────────────────────────────────────────

def _execute_tool(name: str, inp: dict) -> str:
    try:
        if name == "add_to_shopping":
            memory.add_to_shopping(inp.get("items", []))
        elif name == "remove_from_shopping":
            memory.remove_from_shopping(inp.get("items", []))
        elif name == "clear_shopping":
            memory.clear_shopping()
        elif name == "update_inventory":
            memory.update_inventory(inp.get("item", ""), inp.get("status", "є"))
        elif name == "add_to_freezer":
            memory.add_to_freezer(
                name=inp.get("name", ""),
                location=inp.get("location", ""),
                qty=inp.get("qty"),
                unit=inp.get("unit"),
            )
        elif name == "remove_from_freezer":
            memory.remove_from_freezer(inp.get("name", ""), inp.get("qty"))
        elif name == "save_cooking_style":
            kitchen.add_cooking_style(inp.get("tip", ""))
        elif name == "save_recipe":
            kitchen.add_recipe(
                name=inp.get("name", ""),
                ingredients=inp.get("ingredients", []),
                steps=inp.get("steps", ""),
                tags=inp.get("tags", []),
            )
        elif name == "remove_recipe":
            kitchen.remove_recipe(inp.get("name", ""))
        else:
            log.warning(f"Невідомий tool: {name}")
            return f"unknown tool: {name}"
        return "ok"
    except Exception as e:
        log.error(f"_execute_tool {name} помилка: {e}")
        return f"error: {e}"


# ── Helpers ────────────────────────────────────────────────────────────────────

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


async def _summarize_session(user_id: int, history: list) -> str:
    history_text = "\n".join([
        f"{m['role'].upper()}: {str(m.get('content', ''))[:300]}"
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


# ── Main chat ──────────────────────────────────────────────────────────────────

async def chat(user_id: int, user_message: str,
               image_paths: list = None, image_path: str = None) -> str:
    if image_path and not image_paths:
        image_paths = [image_path]
    image_paths = image_paths or []

    history = memory.get_session(user_id)

    if memory.needs_summary(user_id):
        log.info(f"[{user_id}] Сесія {len(history)} повідомлень — стискаємо перед запитом")
        summary = await _summarize_session(user_id, history)
        if summary:
            memory.save_session_with_summary(user_id, history, summary)
            history = memory.get_session(user_id)
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
                content.append({"type": "text", "text": f"[Фото {i+1} з {len(image_paths)}]"})
        except Exception as e:
            log.error(f"Помилка кодування фото {path}: {e}")

    if user_message and len(user_message) > MAX_MSG_LEN:
        user_message = user_message[:MAX_MSG_LEN] + "..."

    if image_paths and not user_message:
        user_message = "Що бачиш на цих фото? Розпізнай і додай в інвентар." if len(image_paths) > 1 else "Що бачиш на фото? Розпізнай і додай в інвентар."
    content.append({"type": "text", "text": user_message})

    optimized.append({"role": "user", "content": content})

    # ── Agentic loop ───────────────────────────────────────────────────────────
    reply_text = ""
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_created = 0

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=build_system(),
            messages=optimized,
            tools=TOOLS,
        )

        u = response.usage
        total_input += u.input_tokens
        total_output += u.output_tokens
        total_cache_read += getattr(u, "cache_read_input_tokens", 0)
        total_cache_created += getattr(u, "cache_creation_input_tokens", 0)

        while response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, block.input)
                    log.info(f"[{user_id}] tool={block.name} input={block.input} result={result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            optimized.append({"role": "assistant", "content": response.content})
            optimized.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=CLAUDE_MAX_TOKENS,
                system=build_system(),
                messages=optimized,
                tools=TOOLS,
            )
            u = response.usage
            total_input += u.input_tokens
            total_output += u.output_tokens
            total_cache_read += getattr(u, "cache_read_input_tokens", 0)
            total_cache_created += getattr(u, "cache_creation_input_tokens", 0)

        for block in response.content:
            if hasattr(block, "text"):
                reply_text = block.text
                break

    except anthropic.APIError as e:
        log.error(f"Anthropic API: {e}")
        return "Сервіс тимчасово недоступний."
    except Exception as e:
        log.error(f"AI помилка: {e}")
        return "Технічна помилка. Спробуй ще раз."

    log.info(
        f"[{user_id}] фото={len(image_paths)} "
        f"in={total_input} out={total_output} "
        f"cache_read={total_cache_read} cache_created={total_cache_created}"
    )
    token_tracker.track(
        input_tokens=total_input,
        output_tokens=total_output,
        cache_read=total_cache_read,
        cache_created=total_cache_created,
        has_image=bool(image_paths),
    )

    history_msg = f"{'[' + str(len(image_paths)) + ' фото] ' if image_paths else ''}{user_message}".strip()
    history.append({"role": "user", "content": history_msg})
    history.append({"role": "assistant", "content": reply_text})
    memory.save_session(user_id, history)

    return reply_text