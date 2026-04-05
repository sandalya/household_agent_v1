# Household Agent — Мег

## Progress Log

**Репо:** https://github.com/sandalya/household_agent_v1
**Pi5 path:** `/home/sashok/.openclaw/workspace/household_agent`
**Systemd:** `household_agent`
**Аліаси:** `meg-status` `meg-restart` `meg-stop` `meg-start` `meg-logs` `meg-git` `meg-freezer`

---

## Стек

* Python 3.11 + venv всередині проекту
* `venv/bin/python3 main.py` — так запускає systemd
* Claude Sonnet (`claude-sonnet-4-5`) via Anthropic API
* python-telegram-bot 21+
* Pillow — стиснення фото перед відправкою в Claude
* faster-whisper (base, cpu, int8) — транскрибація голосових
* JSON файли замість БД (простота і надійність)

---

## Архітектура

    household_agent/
    ├── core/
    │   ├── config.py          # BASE_DIR, .env, ADMIN_IDS, OWNER_CHAT_ID
    │   ├── lock.py            # захист від дублікатів процесів (PID lock)
    │   ├── memory.py          # вся персистентність — read/write JSON
    │   ├── prompt.py          # build_system() — збирає системний промпт з даних
    │   ├── ai.py              # chat() — Claude API, vision, парсинг JSON-команд
    │   ├── kitchen.py         # рецепти, кулінарні підходи, превью
    │   ├── voice.py           # транскрибація голосу через faster-whisper
    │   └── recipe_fetcher.py  # завантаження рецептів по URL
    ├── bot/
    │   └── client.py          # Telegram handlers, буфер 3 сек, grouping фото
    ├── data/
    │   ├── family.json        # профілі сімʼї (заповнено)
    │   ├── inventory.json     # що є вдома
    │   ├── freezer.json       # морозилка і пентрі
    │   ├── shopping_list.json # шоп-ліст
    │   ├── recipes.json       # рецепти і кулінарні підходи
    │   ├── recipe_images/     # превью рецептів
    │   └── sessions.json      # історія розмов по user_id
    ├── logs/
    │   └── bot.log
    ├── PROGRESS.md
    └── main.py

---

## Як працює AI цикл

1. Користувач пише текст, голосове або кидає фото
2. `client.py` буферизує 3 сек (збирає кілька фото в одну пачку)
3. `ai.py chat()` — збирає контент (фото + текст), викликає Claude
4. Claude відповідає текстом + JSON-командами в кінці
5. `_parse_multi_actions()` витягує всі JSON блоки
6. `_execute_action()` виконує кожну дію
7. JSON блоки вирізаються з відповіді, юзер бачить тільки текст

**Доступні дії Claude:**

* `add_to_shopping` / `remove_from_shopping` / `clear_shopping`
* `update_inventory` (статуси: є / мало / нема)
* `add_to_freezer` / `remove_from_freezer`
* `save_cooking_style` / `save_recipe` / `remove_recipe`
* `no_action`

Системний промпт `build_system()` — динамічний, збирається при кожному запиті.
Має `cache_control: ephemeral` для економії токенів.

---

## Що зроблено

### Фаза 1 ✅
* Telegram бот, systemd, lock, логування
* Шоп-ліст: додати / видалити / очистити / переглянути
* Інвентар: статуси є / мало / нема
* Морозилка і пентрі: трекінг по локаціях з датою
* Профілі сімʼї: заповнено (Саша, Ксюша, Сашулік)
* Vision: розпізнавання кількох фото одночасно
* Буфер: збирає кілька фото за 3 сек — один запит до Claude
* Стиснення фото через Pillow (до 1.5MB, якість 82)
* Git repo, аліаси meg-*

### Фаза 2 ✅ (в процесі)
* `/freezer N` — фільтр по ящику в Telegram
* `meg-freezer [N]` — красивий вивід морозилки в PuTTY
* Групування дублів в один рядок (пюре — 1 великий + 1 малий)
* **Голосові повідомлення** — faster-whisper base, локально на Pi5
  + `.ogg` → ffmpeg → `.wav` → Whisper → текст → Claude
  + показує транскрибований текст курсивом перед обробкою
* **Рецепти по URL** — завантажує сторінку, Claude парсить і зберігає
* **Рецепти по фото** — vision читає фото рецепту, зберігає
* **Превью рецептів** — окреме фото після збереження іде як превью
* **Масштабування** — "зроби на 2кг мʼяса" → Claude рахує коефіцієнт
* `meg-git` виправлено як функція з аргументом
* **Menu кнопки** в Telegram — /list, /freezer, /inventory, /recipes, /clear, /reset
* **`/recipes`** — перелік збережених рецептів з тегами і позначкою фото

---

## Що далі

### Фаза 2 — залишилось
* **"Зʼїли X з ящика Y"** — розширити remove_from_freezer з кількістю

### Фаза 3
* **Різноманіття страв** — `cooked_log.json`, трекінг останнього приготування
  + "що давно не готували?" — Мег пропонує забуті страви
* **Metro агент** — авто-збір кошика на metro.zakaz.ua

### Фаза 4
* Проактивні пропозиції на базі паттернів споживання
* Моніторинг акцій Metro
* Щомісячний бюджет

---

## Відомі нюанси

* Фото як документи (не стиснуті) — handle_document()
* Фото як фото (стиснуті Telegram) — handle_photo()
* Голосові — handle_voice(), faster-whisper base
* Превью рецепту: надіслати фото ОКРЕМИМ повідомленням після "Збережено рецепт"
* CLAUDE_MAX_TOKENS = 1024 — розглянути збільшення до 2048
* data/ не в git (.gitignore) — бекап робити окремо

---

## Стиль розробки (для Claude в наступних сесіях)

* Саша спілкується українською
* Готові рішення > обговорення
* Все через SSH команди (PuTTY), великими блоками
* venv завжди: venv/bin/pip, venv/bin/python3
* Після змін: sudo systemctl restart household_agent && meg-logs
* Після стабільного результату: meg-git або git з осмисленим комітом
* При оновленні PROGRESS.md — писати через python -c, не через cat heredoc
* Path стиль: Path(__file__).parent.parent як BASE_DIR
* Логування: log = logging.getLogger("module.name")

---

## Промт для наступної сесії

Продовжуємо розробку Household Agent — бот Мег.
Прочитай файл з повним контекстом:
https://github.com/sandalya/household_agent_v1/blob/main/PROGRESS.md

Коротко: Telegram бот на Pi5, Python + Claude Sonnet + Pillow + faster-whisper,
systemd сервіс household_agent, аліаси meg-*.
Фаза 1 повністю зроблена. Фаза 2 майже готова.
Працюємо через SSH (PuTTY), великими bash блоками, українською.
