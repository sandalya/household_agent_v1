"""Telegram handlers — Household Agent (Мег)."""
import logging
import asyncio
import os
import tempfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
from core.config import TELEGRAM_TOKEN, OWNER_CHAT_ID, ADMIN_IDS
from core import memory
from core import token_tracker
from core import metro
from core.ai import chat
from core import voice
from core import kitchen
from core.recipe_fetcher import fetch_recipe_text, extract_urls

log = logging.getLogger("bot.client")

buffers: dict[int, dict] = {}
BUFFER_WAIT = 3.0

# назва останнього запропонованого рецепту (чекаємо фото превью)
pending_recipe_image: dict[int, str] = {}  # user_id → recipe_name


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
    await _process(update, user_id, buf.get("text", ""), buf.get("image_paths", []))

async def _buffer(user_id: int, update: Update,
                  ctx: ContextTypes.DEFAULT_TYPE,
                  text: str = "", image_path: str = None):
    _cancel_buffer(user_id)
    buf = buffers.setdefault(user_id, {})
    buf["text"] = (buf.get("text", "") + " " + text).strip()
    if image_path:
        buf.setdefault("image_paths", []).append(image_path)
    buf["update"] = update
    buf["task"] = asyncio.create_task(_flush(user_id, update, ctx))


# ── Команди ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    await update.message.reply_text(
        "Привіт, я Мег 🏠\n\n"
        "Пиши що є, що закінчилось, що треба купити.\n"
        "Або скидай фото холодильника — розберусь що є.\n\n"
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

    # фільтр по ящику: /freezer 2
    filter_loc = None
    if ctx.args:
        arg = ctx.args[0].strip()
        filter_loc = f"ящик {arg}" if arg.isdigit() else arg.lower()

    if filter_loc:
        items = [i for i in items if i.get("location", "").lower() == filter_loc]
        if not items:
            await update.message.reply_text(f"В {filter_loc} нічого не знайдено.")
            return

    by_loc: dict[str, list] = {}
    for item in items:
        by_loc.setdefault(item.get("location", "невідомо"), []).append(item)

    def _group_items(loc_items):
        """Групує однакові назви в одному ящику в один рядок."""
        groups = {}
        for i in loc_items:
            key = i["name"].lower().strip()
            groups.setdefault(key, []).append(i)
        result = []
        for key, group in groups.items():
            if len(group) == 1:
                i = group[0]
                i = group[0]
                def _d(qty, unit):
                    u = unit.lower().strip()
                    try: q = int(qty)
                    except: return f"{qty} {unit}"
                    forms = {"малий":("малий","малих","малих"),"великий":("великий","великих","великих"),"пакет":("пакет","пакети","пакетів"),"упаковка":("упаковка","упаковки","упаковок"),"шт":("шт","шт","шт")}
                    if u in forms:
                        if q%10==1 and q%100!=11: f=forms[u][0]
                        elif 2<=q%10<=4 and not(12<=q%100<=14): f=forms[u][1]
                        else: f=forms[u][2]
                        return f"{qty} {f}"
                    return f"{qty} {unit}"
                qty = f" — {_d(i['qty'], i.get('unit','шт'))}" if i.get("qty") else ""
                added = f" _(від {i['added']})_" if i.get("added") and i['added'] != "?" else ""
                result.append(f"  • {i['name']}{qty}{added}")
            else:
                # кілька записів з однаковою назвою — групуємо
                name = group[0]["name"]
                def decline(qty, unit):
                    u = unit.lower().strip()
                    try: q = int(qty)
                    except: return f"{qty} {unit}"
                    forms = {
                        "малий": ("малий", "малих", "малих"),
                        "великий": ("великий", "великих", "великих"),
                        "пакет": ("пакет", "пакети", "пакетів"),
                        "упаковка": ("упаковка", "упаковки", "упаковок"),
                        "шт": ("шт", "шт", "шт"),
                    }
                    if u in forms:
                        if q % 10 == 1 and q % 100 != 11: f = forms[u][0]
                        elif 2 <= q % 10 <= 4 and not (12 <= q % 100 <= 14): f = forms[u][1]
                        else: f = forms[u][2]
                        return f"{qty} {f}"
                    return f"{qty} {unit}"
                parts = []
                for i in group:
                    if i.get("qty"):
                        parts.append(decline(i["qty"], i.get("unit", "шт")))
                # дата — беремо спільну якщо однакова, інакше пропускаємо
                from datetime import datetime
                def parse_date(d):
                    for fmt in ("%d.%m.%y", "%d.%m.%Y"):
                        try: return datetime.strptime(d, fmt)
                        except: pass
                    return datetime.max
                dates = [i["added"] for i in group if i.get("added") and i["added"] != "?"]
                oldest = min(dates, key=parse_date) if dates else None
                added = f" _(від {oldest})_" if oldest else ""
                qty_str = " + ".join(parts) if parts else ""
                result.append(f"  • {name} — {qty_str}{added}" if qty_str else f"  • {name}{added}")
        return result

    total = len(items)
    header = f"❄️ *{filter_loc.capitalize() if filter_loc else 'Морозилка і пентрі'} ({total} позицій):*\n"
    lines = [header]
    for loc, loc_items in sorted(by_loc.items(), key=lambda x: (
        int(x[0].split()[-1]) if x[0].split()[-1].isdigit() else 99
    )):
        lines.append(f"📦 *{loc}*")
        lines.extend(_group_items(loc_items))
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

async def cmd_recipes(update, ctx):
    if not is_authorized(update.effective_user.id):
        return
    data = kitchen.get_recipes()
    recipes = data.get('recipes', [])
    if not recipes:
        await update.message.reply_text('Рецептів ще немає. Скидай посилання або фото рецепту — збережу.')
        return
    lines = ["\U0001f4d6 *Збережені рецепти:*\n"]
    for i, r in enumerate(recipes, 1):
        tags = ', '.join(r['tags']) if r.get('tags') else ''
        tags_str = f' _{tags}_' if tags else ''
        img = ' 📷' if r.get('image') else ''
        lines.append(f"{i}. *{r['name']}*{img}{tags_str}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")



async def cmd_metro(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    items = memory.get_shopping()
    if not items:
        await update.message.reply_text("🛒 Шоп-ліст порожній. Додай товари — і я знайду їх у Metro!")
        return
    inventory = memory.get_inventory()
    suggestions = metro.suggest_missing_items(items, inventory)
    if suggestions:
        top = suggestions[:8]
        ctx.user_data["metro_suggestions"] = top
        ctx.user_data["metro_selected"] = []
        text = "🤔 До речі, ти зазвичай береш, але зараз немає в списку:\nОбери що додати:"
        buttons = []
        for i, s in enumerate(top):
            label = f"☐ {s['title']} ({s['frequency_pct']}%)"
            buttons.append([InlineKeyboardButton(label, callback_data=f"metro_toggle_{i}")])
        buttons.append([
            InlineKeyboardButton("✅ Додати вибране і шукати", callback_data="metro_confirm"),
            InlineKeyboardButton("⏭ Пропустити", callback_data="metro_skip"),
        ])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await run_metro_search(update.message, ctx)


async def callback_metro_suggest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "metro_skip":
        await query.edit_message_text("⏭ Окей, шукаю без змін...")
        await run_metro_search(query.message, ctx)
        return
    if data == "metro_confirm":
        selected = ctx.user_data.get("metro_selected", [])
        suggestions = ctx.user_data.get("metro_suggestions", [])
        if selected:
            to_add = [suggestions[i]["title"] for i in selected]
            memory.add_to_shopping(to_add)
            await query.edit_message_text(f"✅ Додано: {', '.join(to_add)}\n🔍 Шукаю...")
        else:
            await query.edit_message_text("🔍 Шукаю без змін...")
        await run_metro_search(query.message, ctx)
        return
    if data.startswith("metro_toggle_"):
        idx = int(data.split("_")[-1])
        selected = ctx.user_data.get("metro_selected", [])
        if idx in selected:
            selected.remove(idx)
        else:
            selected.append(idx)
        ctx.user_data["metro_selected"] = selected
        top = ctx.user_data.get("metro_suggestions", [])
        buttons = []
        for i, s in enumerate(top):
            mark = "☑" if i in selected else "☐"
            label = f"{mark} {s['title']} ({s['frequency_pct']}%)"
            buttons.append([InlineKeyboardButton(label, callback_data=f"metro_toggle_{i}")])
        buttons.append([
            InlineKeyboardButton("✅ Додати вибране і шукати", callback_data="metro_confirm"),
            InlineKeyboardButton("⏭ Пропустити", callback_data="metro_skip"),
        ])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))


async def run_metro_search(message, ctx):
    items = memory.get_shopping()
    store = metro.get_store()
    token = metro.load_token()
    await message.reply_text(f"🔍 Шукаю {len(items)} товарів у {store['name']}...")
    ean_index = {}
    if token:
        lists = metro.get_lists(token)
        if lists:
            ean_index = metro.build_ean_index(lists)
    try:
        order = metro.build_order_from_shopping_list(items, ean_index=ean_index)
    except metro.MetroUnavailableError as e:
        await message.reply_text(f"⚠️ {e}\n\nСпробуй пізніше — як запрацює, просто напиши /metro знову.")
        return
    if token:
        result = metro.fill_cart_from_order(token, order)
        cart_msg = f"\n\n🛒 Додано в кошик: {result['added']} товарів"
        if result["skipped"]:
            cart_msg += f" (не вдалось: {result['skipped']})"
        cart_msg += "\n👉 Відкрий додаток Metro — кошик вже заповнений!"
    else:
        cart_msg = "\n\n⚠️ Токен не збережено. Надішли /metro\\_auth TOKEN"
    msg = metro.format_order_message(order, store["name"]) + cart_msg
    await message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

async def cmd_analyze_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = metro.load_token()
    if not token:
        await update.message.reply_text('❌ Токен Metro не знайдено. Використай /metro_auth TOKEN')
        return
    await update.message.reply_text('⏳ Завантажую замовлення...')
    orders = metro.get_all_orders(token)
    if not orders:
        await update.message.reply_text('❌ Не вдалося завантажити замовлення. Перевір токен.')
        return
    await update.message.reply_text(f'✅ Знайдено {len(orders)} замовлень. Аналізую...')
    patterns = metro.analyze_purchase_patterns(orders)
    msg = metro.format_patterns_message(patterns)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_metro_auth(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Використання: /metro_auth ТОКЕН")
        return
    token = args[0].strip()
    user_id = update.effective_user.id
    metro.save_token(token, user_id=user_id)
    active = metro.get_active_user()
    nick_msg = f" ({active})" if active else ""
    await update.message.reply_text(f"✅ Токен Metro збережено{nick_msg}! Тепер /metro буде заповнювати кошик.")


async def cmd_metro_ksu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    ok = metro.switch_user("ksu")
    if ok:
        await update.message.reply_text("✅ Переключено на акаунт Ксюші 👩")
    else:
        await update.message.reply_text("❌ Токен Ксюші не збережено. Ксюша має написати /metro_auth ТОКЕН")


async def cmd_metro_sashok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    ok = metro.switch_user("sashok")
    if ok:
        await update.message.reply_text("✅ Переключено на акаунт Сашка 👨")
    else:
        await update.message.reply_text("❌ Токен Сашка не збережено. Напиши /metro_auth ТОКЕН")


async def cmd_metro_who(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    active = metro.get_active_user()
    users = metro.get_saved_users()
    saved = ", ".join(users.keys()) if users else "немає"
    if active:
        msg = f"🔑 Активний акаунт Metro: *{active}*\nЗбережені: {saved}"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        msg2 = f"⚠️ Активний акаунт не вибрано\nЗбережені: {saved}"
        await update.message.reply_text(msg2)



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
    if not text:
        return

    # перевіряємо чи є URL — якщо так, завантажуємо сторінку
    urls = extract_urls(text)
    if urls:
        await update.message.reply_text("🔗 Завантажую сторінку...")
        fetched_parts = []
        for url in urls[:2]:  # максимум 2 посилання за раз
            page_text = fetch_recipe_text(url)
            if page_text:
                fetched_parts.append(f"[Вміст сторінки {url}]: " + page_text)

            else:
                fetched_parts.append(f"[Не вдалось завантажити {url}]")
        if fetched_parts:
            text = text + "\n\n" + "\n\n".join(fetched_parts)


    await _buffer(user_id, update, ctx, text=text)

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return
    caption = (update.message.caption or "").strip()
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    tmp_path = os.path.join(tempfile.gettempdir(), f"meg_{user_id}_{photo.file_unique_id}.jpg")
    await file.download_to_drive(tmp_path)
    log.info(f"Фото завантажено: {tmp_path}")

    # чекаємо фото превью (окреме фото після збереження рецепту)
    if user_id in pending_recipe_image and not caption:
        recipe_name = pending_recipe_image.pop(user_id)
        if recipe_name:
            ok = kitchen.save_recipe_image(recipe_name, tmp_path)
            if ok:
                await update.message.reply_text(f"📷 Превью збережено для *{recipe_name}*", parse_mode="Markdown")
                return
        await update.message.reply_text("Не знайшла рецепт для цього фото.")
        return

    await _buffer(user_id, update, ctx, text=caption, image_path=tmp_path)

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return
    doc = update.message.document
    if not (doc.mime_type and doc.mime_type.startswith("image/")):
        await update.message.reply_text("Надсилай фото або зображення.")
        return
    caption = (update.message.caption or "").strip()
    file = await ctx.bot.get_file(doc.file_id)
    suffix = Path(doc.file_name).suffix if doc.file_name else ".jpg"
    tmp_path = os.path.join(tempfile.gettempdir(), f"meg_doc_{user_id}_{doc.file_unique_id}{suffix}")
    await file.download_to_drive(tmp_path)
    log.info(f"Документ-фото завантажено: {tmp_path}")
    await _buffer(user_id, update, ctx, text=caption, image_path=tmp_path)


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return
    import tempfile, os
    v = update.message.voice
    file = await ctx.bot.get_file(v.file_id)
    tmp_path = os.path.join(tempfile.gettempdir(), f"meg_voice_{user_id}_{v.file_unique_id}.ogg")
    await file.download_to_drive(tmp_path)
    log.info(f"Голосове завантажено: {tmp_path}")
    await update.message.reply_text("🎙️ Слухаю...")
    text = voice.transcribe(tmp_path)
    if not text:
        await update.message.reply_text("Не розібрала. Спробуй ще раз або напиши текстом.")
        return
    log.info(f"Голос → текст: {text}")
    await update.message.reply_text(f'🎙️ _"{text}"_', parse_mode='Markdown')
    await _buffer(user_id, update, ctx, text=text)


async def _process(update: Update, user_id: int,
                   message: str, image_paths: list = None):
    if not message and not image_paths:
        return

    n = len(image_paths) if image_paths else 0
    await update.message.reply_chat_action("typing")

    reply = await chat(user_id, message, image_paths=image_paths)
    await update.message.reply_text(reply)

    # якщо Claude щойно зберіг рецепт — запам'ятовуємо що наступне фото = превью
    # якщо Claude щойно зберіг рецепт — наступне фото буде превью
    if "збережено рецепт" in reply.lower() or "зберігаю рецепт" in reply.lower():
        last = kitchen.get_last_recipe_name()
        if last:
            pending_recipe_image[user_id] = last
            log.info(f"Чекаємо фото превью для: {last}")


# ── Setup ─────────────────────────────────────────────────────────────────────

async def post_init(app):
    await app.bot.set_my_commands([
        ("list",      "🛒 Шоп-ліст"),
        ("freezer",   "❄️ Морозилка і пентрі"),
        ("inventory", "🏠 Що є вдома"),
        ("recipes",   "📖 Збережені рецепти"),
        ("clear",     "🗑 Очистити шоп-ліст"),
        ("reset",     "🔄 Скинути сесію"),
    ])


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = token_tracker.format_stats(days=7)
    await update.message.reply_text(text)

def setup_handlers(app: Application):
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("list",      cmd_list))
    app.add_handler(CommandHandler("freezer",   cmd_freezer))
    app.add_handler(CommandHandler("inventory", cmd_inventory))
    app.add_handler(CommandHandler("recipes",   cmd_recipes))
    app.add_handler(CommandHandler("metro",     cmd_metro))
    app.add_handler(CommandHandler("metro_auth", cmd_metro_auth))
    app.add_handler(CallbackQueryHandler(callback_metro_suggest, pattern="^metro_"))
    app.add_handler(CommandHandler("metro_ksu",  cmd_metro_ksu))
    app.add_handler(CommandHandler("metro_sashok", cmd_metro_sashok))
    app.add_handler(CommandHandler("metro_who",  cmd_metro_who))
    app.add_handler(CommandHandler("analyze_orders", cmd_analyze_orders))
    app.add_handler(CommandHandler("clear",     cmd_clear))
    app.add_handler(CommandHandler("reset",     cmd_reset))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    log.info("Handlers налаштовано")
