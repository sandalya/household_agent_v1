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
    │   ├── recipe_fetcher.py  # завантаження рецептів по URL
    │   └── metro.py           # Metro агент — пошук товарів, кошик
    ├── bot/
    │   └── client.py          # Telegram handlers, буфер 3 сек, grouping фото
    ├── data/
    │   ├── family.json        # профілі сімʼї (заповнено)
    │   ├── inventory.json     # що є вдома
    │   ├── freezer.json       # морозилка і пентрі
    │   ├── shopping_list.json # шоп-ліст
    │   ├── recipes.json       # рецепти і кулінарні підходи
    │   ├── recipe_images/     # превью рецептів
    │   ├── metro_config.json  # токен і налаштування Metro
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
* `add_to_freezer` / `remove_from_freezer` (з qty — зменшує кількість)
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

### Фаза 2 ✅
* `/freezer N` — фільтр по ящику в Telegram
* `meg-freezer [N]` — красивий вивід морозилки в PuTTY
* Групування дублів в один рядок з найстарішою датою
* Правильне відмінювання: 1 малий, 2 малих, 5 малих
* **Голосові повідомлення** — faster-whisper base, локально на Pi5
* **Рецепти по URL** — завантажує сторінку, Claude парсить і зберігає
* **Рецепти по фото** — vision читає фото рецепту, зберігає
* **Превью рецептів** — окреме фото після збереження іде як превью
* **Масштабування** — "зроби на 2кг мʼяса" → Claude рахує коефіцієнт
* **`/recipes`** — перелік збережених рецептів з тегами
* **Menu кнопки** в Telegram — /list, /freezer, /inventory, /recipes, /clear, /reset
* **remove_from_freezer з qty** — зменшує кількість а не видаляє весь запис
* **add_to_freezer** — додає нову партію окремим рядком (не перезаписує)
* **Souper Cubes** — збережено в cooking_style, Мег знає що малий/великий = кубики
* `meg-git` виправлено як функція з аргументом

### Фаза 3 ✅
* `core/metro.py` — повний Metro клієнт через неофіційний API (stores-api.zakaz.ua)
* Три магазини Metro Київ: Позняки (default), Теремки, Троєщина
* Авторизація через cookie `__Host-zakaz-sid` (береться з браузера один раз)
* Збереження токена в `data/metro_config.json`
* `search_product` — пошук товарів по запиту (per_page=5)
* `pick_best_product` — Claude вибирає найкращий варіант з кандидатів
* `_parse_quantity` — парсинг кількості: "морква 6 шт" → 0.6кг, "яйця 14шт" → упаковка
* `fill_cart_from_order` — очищає кошик (operation=set amount=0) і заповнює новими товарами
* `/metro` команда в Telegram — шукає весь шоп-ліст і автоматично заповнює кошик
* Підтримка знижок — показує стару ціну і відсоток знижки

**API endpoints:**
* Search: `GET /stores/{id}/products/search/?per_page=5&q={query}`
* Cart read: `GET /cart/` + `X-Chain: metro`
* Cart write: `POST /cart/items/` + `{items: [{ean, amount, operation}]}`
  - `operation="add"` — додати товар
  - `operation="set" amount=0` — видалити товар

**Відомі нюанси Metro:**
* Токен треба оновлювати вручну (~раз на 2 місяці), команда `/metro_auth TOKEN` — TODO
* Морква та інші вагові (unit=kg) — "6 шт" конвертується в 0.6кг
* Два записи яєць в шоп-листі → дві різні упаковки в кошику (нормальна поведінка)
* Ціни в API зберігаються в копійках (divide by 100)

---

## Що далі

### Фаза 3 ✅
* **Metro агент** — повністю реалізовано (див. нижче)

### Фаза 4
* **Різноманіття страв** — `cooked_log.json`, трекінг останнього приготування
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
Фаза 1, Фаза 2 і Фаза 3 повністю зроблені.
Працюємо через SSH (PuTTY), великими bash блоками, українською.
