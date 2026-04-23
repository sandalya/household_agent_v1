---
project: household_agent
created: 2026-04-23
---

# COLD — household_agent

Архів завершених фаз, міграцій, рефакторингів. Append-only: нові записи додаються вниз з датою.

---

## 2026-04-23 — Ініціалізація триярусної пам'яті

Проект переведено на структуру HOT/WARM/COLD/MEMORY. Створено через `chkp --init household_agent`. Rule Zero прийнято. Попередній стан виведено з userMemories Claude + поточної структури проекту.

