## 📄 `05_DDR.md`
```markdown
# Detailed Design Review (DDR)

## 1. Orchestrator State Machine
- INIT
- DISPATCH
- COLLECT
- VALIDATE
- COMMIT
- ROLLBACK

---

## 2. Retry Logic
- Max retries per agent: configurable
- Exponential backoff
- Retry only idempotent tasks

---

## 3. Git Operations
- Clone to temp workspace
- Branch per task
- No direct main writes
- Merge only after gates

---

## 4. Directory Layout
```text
runtime/
├── orchestrator/
├── agents/
│   ├── engineer/
│   ├── qa/
│   └── security/
├── redis/
└── logs/
