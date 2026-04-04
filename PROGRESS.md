# Household Agent — Мег
## Progress Log

**Репо:** https://github.com/sandalya/household_agent_v1
**Pi5 path:** `/home/sashok/.openclaw/workspace/household_agent`
**Systemd:** `household_agent`
**Аліаси:** `meg-status` `meg-restart` `meg-stop` `meg-start` `meg-logs` `meg-git`

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

household_agent/
├── core/
│   ├── config.py      # BASE_DIR, .env, ADMIN_IDS, OWNER_CHAT_ID
│   ├── lock.py        # захист від дублікатів процесів (PID lock)
│   ├── memory.py      # вся персистентність — read/write JSON
│   ├── prompt.py      # build_system() — збирає системний промпт з даних
│   └── ai.py          # chat() — Claude API, vision, парсинг JSON-команд
├── bot/
│   └── client.py      # Telegram handlers, буфер 3 сек, grouping фото
├── data/
│   ├── family.json        # профілі сім'ї (поки шаблон, не заповнено)
│   ├── inventory.json     # що є вдома (заповнено через фото)
│   ├── freezer.json       # морозилка і пентрі
│   ├── shopping_list.json # шоп-ліст
│   └── sessions.json      # історія розмов по user_id
├── logs/
│   └── bot.log
├── PROGRESS.md
└── main.py

---

## Як працює AI цикл

1. Користувач пише текст або кидає фото
2. `client.py` буферизує 3 сек (збирає кілька фото в одну пачку)
3. `ai.py chat()` — збирає контент (фото + текст), викликає Claude
4. Claude відповідає текстом + JSON-командами в кінці
5. `_parse_multi_actions()` витягує всі JSON блоки
6. `_execute_action()` виконує кожну дію
7. JSON блоки вирізаються з відповіді, юзер бачить тільки текст

**Доступні дії Claude:**
- `add_to_shopping` / `remove_from_shopping` / `clear_shopping`
- `update_inventory` (статуси: є / мало / нема)
- `add_to_freezer` / `remove_from_freezer`
- `no_action`

Системний промпт `build_system()` — динамічний, збирається при кожному запиті.
Має `cache_control: ephemeral` для економії токенів.

---

## Що зроблено (Фаза 1)

- [x] Telegram бот, systemd, lock, логування
- [x] Шоп-ліст: додати / видалити / очистити / переглянути
- [x] Інвентар: статуси є / мало / нема
- [x] Морозилка і пентрі: трекінг по локаціях з датою
- [x] Профілі сім'ї: структура є, дані не заповнені
- [x] Vision: розпізнавання кількох фото одночасно
- [x] Буфер: збирає кілька фото за 3 сек — один запит до Claude
- [x] Стиснення фото через Pillow (до 1.5MB, якість 82)
- [x] Унікальні tmp файли (file_unique_id)
- [x] Git repo, аліаси meg-*

Перший реальний тест: Мег розпізнала 10+ фото холодильника,
пентрі і морозилки — розбила по полицях, додала в інвентар.

---

## Що далі (Фаза 2)

### Першочергово
- [ ] Заповнити `data/family.json` реальними іменами і вподобаннями
- [ ] Кулінарний мозок: новий модуль `core/kitchen.py`
  - рецепти і підходи до готування
  - що приготувати з того що є — на базі inventory.json
  - навчання: ми завжди смажимо цибулю на вершковому — запам'ятовує
- [ ] Планування заготовок
  - режим плануємо заготовки — меню страв під заморозку
  - авто-шоп-ліст для заготовок
  - після готування — оновлює freezer.json

### Фаза 3
- [ ] Metro агент: авто-збір кошика на metro.zakaz.ua
- [ ] Підтвердження замовлення користувачем

### Фаза 4
- [ ] Проактивні пропозиції на базі паттернів споживання
- [ ] Моніторинг акцій Metro
- [ ] Щомісячний бюджет

---

## Відомі нюанси

- Фото як документи (не стиснуті) — handle_document()
- Фото як фото (стиснуті Telegram) — handle_photo()
- Обидва хендлери ведуть в один буфер — один запит
- CLAUDE_MAX_TOKENS = 1024 — розглянути збільшення до 2048
  якщо відповіді обрізаються при великій кількості фото
- data/ не в git (.gitignore) — бекап робити окремо

---

## Стиль розробки (для Claude в наступних сесіях)

- Саша спілкується українською
- Готові рішення > обговорення
- Все через SSH команди (PuTTY), великими блоками
- venv завжди: venv/bin/pip, venv/bin/python3
- Після змін: sudo systemctl restart household_agent && meg-logs
- Після стабільного результату: meg-git або git з осмисленим комітом
- Path стиль: Path(__file__).parent.parent як BASE_DIR
- Логування: log = logging.getLogger('module.name')

---

## Промт для наступної сесії

Продовжуємо розробку Household Agent — бот Мег.

Прочитай файл з повним контекстом:
https://github.com/sandalya/household_agent_v1/blob/main/PROGRESS.md

Коротко: Telegram бот на Pi5, Python + Claude Sonnet + Pillow,
systemd сервіс household_agent, аліаси meg-*.
Фаза 1 повністю зроблена — шоп-ліст, інвентар, морозилка,
розпізнавання кількох фото одночасно.

Працюємо через SSH (PuTTY), великими bash блоками, українською.

Сьогодні беремось за Фазу 2: кулінарний мозок і профілі сім'ї.
Починай з того що попросиш мене показати поточний стан
data/family.json і data/inventory.json — щоб розуміти з чим працюємо.
