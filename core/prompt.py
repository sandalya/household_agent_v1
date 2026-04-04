"""Системний промпт Household Agent."""
from core.memory import get_family, get_inventory, get_shopping, get_freezer

SYSTEM_BASE = """
Ти — домашній асистент сім'ї. Звати тебе Мег.

Допомагаєш вести побут: трекаєш що є вдома, що треба купити, що лежить у морозилці.
Відповідаєш лаконічно, по ділу. Без захоплень і підлабузництва.
Мова: українська. Якщо написали російською — відповідай українською.

## Сім'я
{family}

## Інвентар (що є вдома)
{inventory}

## Шоп-ліст
{shopping}

## Морозилка і пентрі
{freezer}

---

## Як працюєш

Розумієш природну мову. "купи молоко", "закінчилось масло", "що в морозилці?" — все ок.

Після кожної дії повертаєш JSON-команду в кінці відповіді:
```json
{{"action": "назва", "data": {{}}}}
```

Дії:
- add_to_shopping      → data: {{"items": ["молоко", "хліб"]}}
- remove_from_shopping → data: {{"items": ["молоко"]}}
- clear_shopping       → data: {{}}
- update_inventory     → data: {{"item": "масло", "status": "нема"}}  (є / мало / нема)
- add_to_freezer       → data: {{"name": "борщ", "location": "морозилка/ящик 1", "qty": 4, "unit": "порції"}}
- remove_from_freezer  → data: {{"name": "борщ"}}
- no_action            → data: {{}}

Якщо тільки питання (що є? що купити?) — відповідай і повертай no_action.
Не вигадуй що є вдома якщо цього немає в контексті.
"""

def build_system() -> list:
    """Повертає блоки для system= з cache_control на статичній частині."""
    family = get_family()
    inventory = get_inventory()
    shopping = get_shopping()
    freezer = get_freezer()

    # Сім'я
    if family:
        fam_lines = []
        for name, info in family.items():
            likes    = ", ".join(info.get("likes", [])) or "—"
            dislikes = ", ".join(info.get("dislikes", [])) or "—"
            notes    = info.get("notes", "")
            fam_lines.append(
                f"- {name}: любить [{likes}], не їсть [{dislikes}]"
                + (f". {notes}" if notes else "")
            )
        fam_str = "\n".join(fam_lines)
    else:
        fam_str = "Не заповнено."

    # Інвентар
    if inventory:
        inv_str = "\n".join(f"- {k}: {v}" for k, v in inventory.items())
    else:
        inv_str = "Порожньо."

    # Шоп-ліст
    shop_str = "\n".join(f"- {i}" for i in shopping) if shopping else "Порожній."

    # Морозилка
    if freezer:
        frz_lines = []
        for item in freezer:
            qty   = f"{item['qty']} {item.get('unit','шт')}" if item.get("qty") else ""
            added = f" (від {item['added']})" if item.get("added") else ""
            frz_lines.append(
                f"- {item['name']} → {item['location']}"
                + (f", {qty}" if qty else "") + added
            )
        frz_str = "\n".join(frz_lines)
    else:
        frz_str = "Порожньо."

    dynamic_text = SYSTEM_BASE.format(
        family=fam_str, inventory=inv_str,
        shopping=shop_str, freezer=frz_str
    )

    return [
        {
            "type": "text",
            "text": dynamic_text,
            "cache_control": {"type": "ephemeral"}
        }
    ]
