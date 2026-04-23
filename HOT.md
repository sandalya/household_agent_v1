---
project: household_agent
updated: 2026-04-23
---

# HOT — household_agent

## Now

Щойно ініціалізовано через chkp --init. Триярусна памʼять активована.

## Last done

**2026-04-23** — Міграція на HOT/WARM/COLD/MEMORY структуру. Rule Zero прийнято.

## Next

1. Заповнити WARM.md реальною архітектурою проекту.
2. Провести першу робочу сесію + чекпоінт через chkp.

## Blockers

Немає.

## Active branches

- **household_agent-репо** (`main`): Стан гілки — уточнити.

## Open questions

Немає.

## Reminders

- Workspace: `/home/sashok/.openclaw/workspace/household_agent/`
- Перед тестуванням бота — `journalctl -u household_agent -f` ДО надсилання повідомлення
- API keys маскувати до останніх 4 символів
- Checkpoint: `chkp household_agent "..." "..." "..."`
