# Household Agent — Мег

## Progress Log

**Репо:** https://github.com/sandalya/household_agent_v1
**Pi5 path:** `/home/sashok/.openclaw/workspace/household_agent`
**Systemd:** `household_agent`
**Аліаси:** `meg-status` `meg-restart` `meg-stop` `meg-start` `meg-logs` `meg-git` `meg-check`

---

## Стек

- Python 3.11 + venv всередині проекту
- `venv/bin/python3 main.py` — так запускає systemd
- Claude Sonnet (`claude-sonnet-4-5`) via Anthropic API
- python-telegram-bot 21+
- Pillow — стиснення фото перед відправкою в Claude
- JSON файли замість БД (простота і надійність)

---

## Архітектура

core/config.py — BASE_DIR, .env, ADMIN_IDS, OWNER_CHAT_ID
core/lock.py — захист від дублікатів процесів (PID lock)
core/memory.py — вся персистентність, read/write JSON
core/prompt.py — build_system(), збирає системний промпт з даних
core/ai.py — chat(), Claude API, vision, парсинг JSON-команд
core/kitchen.py — кулінарний мозок, рецепти, стилі готування
core/metro.py — Metro агент, пошук, кошик, токен
core/recipe_fetcher.py — завантаження рецептів по URL
core/token_tracker.py — статистика використання токенів
core/voice.py — голосові повідомлення через faster-whisper
bot/client.py — Telegram handlers, буфер 3 сек, grouping фото
data/family.json — профілі сім'ї
data/inventory.json — що є вдома
data/freezer.json — морозилка і пентрі
data/shopping_list.json — шоп-ліст
data/sessions.json — історія розмов по user_id
data/metro_config.json — токен і магазин Metro
logs/bot.log
SOUL.md — душа Мег, характер, межі, пам'ять
PROGRESS.md
main.py

---

## Як працює AI цикл

1. Користувач пише текст або кидає фото
2. client.py буферизує 3 сек (збирає кілька фото в одну пачку)
3. ai.py chat() збирає контент (фото + текст), викликає Claude
4. Claude відповідає текстом + JSON-командами в кінці
5. _parse_multi_actions() витягує всі JSON блоки
6. _execute_action() виконує кожну дію
7. JSON блоки вирізаються з відповіді, юзер бачить тільки текст

Доступні дії Claude:
- add_to_shopping / remove_from_shopping / clear_shopping
- update_inventory (статуси: є / мало / нема)
- add_to_freezer / remove_from_freezer
- save_cooking_style / save_recipe / remove_recipe
- no_action

Системний промпт build_system() — динамічний, збирається при кожному запиті.
Має cache_control: ephemeral для економії токенів.

---

## Фази розробки

### Фаза 1 — Базовий бот (DONE)
- Telegram бот, systemd, lock, логування
- Шоп-ліст: додати / видалити / очистити / переглянути
- Інвентар: статуси є / мало / нема
- Морозилка і пентрі: трекінг по локаціях з датою
- Профілі сім'ї
- Vision: розпізнавання кількох фото одночасно
- Буфер: збирає кілька фото за 3 сек, один запит до Claude
- Стиснення фото через Pillow (до 1.5MB, якість 82)

### Фаза 2 — Кулінарний мозок (DONE)
- core/kitchen.py — рецепти, стилі готування, історія покупок
- Збереження рецептів по посиланню і фото
- Масштабування рецептів
- Планування заготовок
- core/voice.py — голосові повідомлення через faster-whisper

### Фаза 3 — Metro агент (DONE)
- core/metro.py — пошук товарів через stores-api.zakaz.ua
- pick_best_product() — Claude вибирає найкращий варіант
- Автозаповнення кошика через токен сесії
- /metro — збирає кошик зі шоп-листа
- /metro_auth TOKEN — зберігає токен
- Інструкція як знайти токен вбудована в промпт Мег

### Фаза 4 — Душа і полірування (DONE)
- SOUL.md — характер Мег: думки, межі, пам'ять, ставлення до сім'ї
- Підключено до SYSTEM_STATIC через prompt.py
- Замінено ⏳ на typing... (Telegram chat action)
- meg-check аліас для швидкого перегляду логів без -f

---

## Відомі нюанси

- Фото як документи (не стиснуті) — handle_document()
- Фото як фото (стиснуті Telegram) — handle_photo()
- Обидва хендлери ведуть в один буфер — один запит
- CLAUDE_MAX_TOKENS = 1024 — розглянути збільшення до 2048
- data/ не в git (.gitignore) — бекап робити окремо
- Токен Metro — кукі __Host-zakaz-sid з metro.zakaz.ua (DevTools → Application → Cookies)
- meg-logs використовує tail -f — виходити через Ctrl+C
- meg-check — tail -20 для швидкого погляду без -f

---

## Стиль розробки

- Саша спілкується українською
- Готові рішення > обговорення
- Все через SSH команди (PuTTY), великими блоками
- venv завжди: venv/bin/pip, venv/bin/python3
- Після змін: sudo systemctl restart household_agent && sleep 3 && meg-logs
- Після стабільного результату: meg-git або git з осмисленим комітом
- Path стиль: Path(__file__).parent.parent як BASE_DIR
- Логування: log = logging.getLogger('module.name')
- ВАЖЛИВО: великі файли писати через python3 -c, не через cat heredoc — heredoc розбивається на кілька блоків у веб-інтерфейсі Claude і неможливо скопіювати

---

## Промпт для наступної сесії

Продовжуємо розробку Household Agent — бот Мег.
Прочитай файл з повним контекстом:
https://github.com/sandalya/household_agent_v1/blob/main/PROGRESS.md

Коротко: Telegram бот на Pi5, Python + Claude Sonnet + Pillow + faster-whisper,
systemd сервіс household_agent, аліаси meg-*.
Фаза 1, Фаза 2, Фаза 3 і Фаза 4 повністю зроблені.
Працюємо через SSH (PuTTY), великими bash блоками, українською.
