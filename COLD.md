---
project: household_agent
created: 2026-04-23
---

# COLD — household_agent

Архів завершених фаз, міграцій, рефакторингів. Append-only: нові записи додаються вниз з датою.

---

## 2026-04-23 — Ініціалізація триярусної пам'яті

Проект переведено на структуру HOT/WARM/COLD/MEMORY. Створено через `chkp --init household_agent`. Rule Zero прийнято. Попередній стан виведено з userMemories Claude + поточної структури проекту.

---

## 2026-05-04 — Disk cleanup сесія (git filter-repo, gallery-dl removal)

```yaml
archived_at: 2026-05-04
reason: completed, infrastructure maintenance
tags: [cleanup, git, disk-space, infrastructure]
```

Очищено 551M диска: `git filter-repo` видалив gallery-dl/ з історії (240M→612K, 400x reduction), force-push origin, фізичне rm -rf (311M). venv 3G норма. Working tree чистий, production-safe. gallery-dl/ → .gitignore. Меггі-сервіс не рестартувався, JSON-стан + бази даних цілі. Сесія не містила runtime/logic змін.
