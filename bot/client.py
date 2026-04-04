"""Telegram handlers — Household Agent."""
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from core.config import TELEGRAM_TOKEN, OWNER_CHAT_ID, ADMIN_IDS
from core import memory
from core.ai import chat

log = logging.getLogger("bot.client")

# message grouping
buffers: dict[int, dict] = {}
BUFFER_WAIT = 2.0


def is_authorized(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == OWNER_CHAT_ID


# ── Grouping ──────────────────────────────────────────────────────────────────

def _cancel_buffer(user_id: int):
    if user_id in buffers and buffers[user_id].get("task"):
        buffers[user_id]["task"].cancel()

async def _flush(user_id: int, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(BUFFER_WAIT)
    buf = buffers.pop(user_id, None)
    if not buf:
        return
    await _process(update, user_id, buf.get("text", ""))

async def _buffer(user_id: int, update: Update,
                  ctx: ContextTypes.DEFAULT_TYPE, text: str):
    _cancel_buffer(user_id)
    buf = buffers.setdefault(user_id, {})
    buf["text"] = (buf.get("text", "") + " " + text).strip()
    buf["update"] = update
    buf["task"] = asyncio.create_task(_flush(user_id, update, ctx))


# ── Команди ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    await update.message.reply_text(
        "Привіт, я Мег 🏠\n\n"
        "Просто пиши що є, що закінчилось, що треба купити.\n\n"
        "/list — шоп-ліст\n"
        "/freezer — морозилка і пентрі\n"
        "/inventory — що є вдома\n"
        "/clear — очистити шоп-ліст\n"
        "/reset — скинути сесію"
    )

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    items = memory.get_shopping()
    if not items:
        await update.message.reply_text("Шоп-ліст порожній ✓")
        return
    text = "🛒 *Треба купити:*\n" + "\n".join(f"• {i}" for i in items)
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_freezer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    items = memory.get_freezer()
    if not items:
        await update.message.reply_text("Морозилка і пентрі порожні.")
        return
    by_loc: dict[str, list] = {}
    for item in items:
        by_loc.setdefault(item.get("location", "невідомо"), []).append(item)
    lines = ["❄️ *Морозилка і пентрі:*\n"]
    for loc, loc_items in sorted(by_loc.items()):
        lines.append(f"*{loc}*")
        for i in loc_items:
            qty   = f" — {i['qty']} {i.get('unit','шт')}" if i.get("qty") else ""
            added = f" _(від {i['added']})_" if i.get("added") else ""
            lines.append(f"  • {i['name']}{qty}{added}")
        lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_inventory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    inv = memory.get_inventory()
    if not inv:
        await update.message.reply_text("Інвентар порожній.")
        return
    emoji = {"є": "✅", "мало": "⚠️", "нема": "❌"}
    lines = ["🏠 *Що є вдома:*\n"]
    for item, status in sorted(inv.items()):
        lines.append(f"{emoji.get(status,'•')} {item} — {status}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    memory.clear_shopping()
    await update.message.reply_text("Шоп-ліст очищено ✓")

async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    memory.clear_session(update.effective_user.id)
    await update.message.reply_text("Сесію скинуто.")


# ── Повідомлення ──────────────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return
    text = (update.message.text or "").strip()
    if text:
        await _buffer(user_id, update, ctx, text)

async def _process(update: Update, user_id: int, message: str):
    if not message:
        return
    await update.message.reply_text("⏳")
    reply = await chat(user_id, message)
    await update.message.reply_text(reply)


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("list",      cmd_list))
    app.add_handler(CommandHandler("freezer",   cmd_freezer))
    app.add_handler(CommandHandler("inventory", cmd_inventory))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(CommandHandler("reset",     cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Handlers налаштовано")
