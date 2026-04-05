"""Кулінарний мозок — рецепти, підходи, заготовки."""
import logging
from core.memory import _load, _save

log = logging.getLogger("core.kitchen")


def get_recipes() -> dict:
    return _load("recipes.json", {"cooking_style": [], "recipes": []})


def add_cooking_style(tip: str):
    """Запам'ятати кулінарний підхід сім'ї."""
    data = get_recipes()
    tip = tip.strip()
    if tip and tip not in data["cooking_style"]:
        data["cooking_style"].append(tip)
        _save("recipes.json", data)
        log.info(f"Додано кулінарний підхід: {tip}")


def add_recipe(name: str, ingredients: list, steps: str, tags: list = None):
    """Зберегти рецепт."""
    data = get_recipes()
    # Оновлюємо якщо вже є
    data["recipes"] = [r for r in data["recipes"] if r["name"].lower() != name.lower()]
    data["recipes"].append({
        "name": name.strip(),
        "ingredients": ingredients,
        "steps": steps.strip(),
        "tags": tags or []
    })
    _save("recipes.json", data)
    log.info(f"Збережено рецепт: {name}")


def remove_recipe(name: str):
    data = get_recipes()
    data["recipes"] = [r for r in data["recipes"] if r["name"].lower() != name.lower()]
    _save("recipes.json", data)


def get_purchase_history() -> dict:
    return _load("purchase_history.json", {})


def format_for_prompt() -> str:
    """Форматує кулінарні дані для системного промпту."""
    data = get_recipes()
    lines = []

    if data.get("cooking_style"):
        lines.append("**Наші підходи до готування:**")
        for tip in data["cooking_style"]:
            lines.append(f"- {tip}")

    recipes = data.get("recipes", [])
    if recipes:
        lines.append(f"\n**Збережені рецепти ({len(recipes)} шт):**")
        for r in recipes:
            tags = f" [{', '.join(r['tags'])}]" if r.get("tags") else ""
            ingr = ", ".join(r.get("ingredients", []))
            lines.append(f"- {r['name']}{tags}: {ingr}")
    else:
        lines.append("\n**Рецепти:** поки не збережені.")

    return "\n".join(lines) if lines else "Не заповнено."


def format_purchase_history_for_prompt() -> str:
    """Форматує список звичних покупок для промпту."""
    history = get_purchase_history()
    if not history:
        return "Не заповнено."
    lines = []
    for cat_data in history.values():
        label = cat_data.get("label", "")
        items = ", ".join(cat_data.get("items", []))
        lines.append(f"**{label}:** {items}")
    return "\n".join(lines)
