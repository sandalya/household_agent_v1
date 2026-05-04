---
project: household_agent
updated: 2026-05-04
---

# HOT — household_agent

## Now

Диск очищено (git filter-repo, 551M вільно). Меггі-сервіс не торкались, production стійкий. Готуємось до повернення на Sam external_stop fix (завтра). Меггі — наступне архітектурне торкання після того.

## Last done

**2026-05-04** — Disk cleanup сесія:
- `git filter-repo` видалив gallery-dl/ з історії (240M→612K, 400x reduction)
- Force-push origin + фізичне rm -rf gallery-dl/ (311M додатково)
- Total economy: 551M
- venv 3G норма (PTB/openai/ML deps окей)
- Working tree чистий, production-safe

## Next

1. Завтра ранок: Sam external_stop zombie pending fix (P3, 15 хв через CC)
2. Після Sam добʼємо — повернутись до Меггі (архітектурне торкання або нова фіча)
3. gallery-dl/ в .gitignore, безпечно для наступних data-сесій

## Blockers

Немає.

## Active branches

- **household_agent-репо** (`main`): Чистий, production-ready, без pending commits

## Open questions

Немає поточних архітектурних питань.

## Reminders

- Workspace: `/home/sashok/.openclaw/workspace/household_agent/`
- Перед тестуванням бота — `journalctl -u household_agent -f` ДО надсилання повідомлення
- API keys маскувати до останніх 4 символів
- Checkpoint: `chkp household_agent "..." "..." "..."`
- gallery-dl/ більше не в repo історії, не турбуватись про розмір
