# docs_legacy

В этой папке лежат документы, убранные из активного `docs/` в рамках refresh документации.

Причина переноса: эти файлы содержали устаревшие ссылки на несуществующие пути (`apps/desktop/src/api.ts`, `MainApp.tsx`, `OverlayApp.tsx` и т.п.), дублировали друг друга или описывали точечные аудиты/состояние на конкретный момент.

## Чем заменено

| Legacy doc group | Причина переноса | Актуальная замена |
|---|---|---|
| `STATE_*`, `STABILIZATION_PLAN.md`, `DOD.md`, `FIXLOG.md` | point-in-time статус, не эксплуатационная документация | `../README.md`, `../docs/ARCHITECTURE.md`, `../docs/TROUBLESHOOTING.md` |
| `*_AUDIT*.md`, `ARCHITECTURE_MAP.md`, `FRONTEND_BACKEND_OVERVIEW.md` | аудитные снимки и дубли архитектуры | `../docs/ARCHITECTURE.md`, `../docs/CONFIG.md` |
| `UI_GUIDE.md`, `OVERLAY_V1.md`, `RUNBOOK_DEV.md` | ссылки на старую структуру desktop | `../README.md`, `../docs/DEVELOPMENT.md`, `../docs/TROUBLESHOOTING.md` |
| `MEMORY_V1.md`, `REMINDERS_V1.md`, `PLANNER_V1.md`, `EXECUTOR_LOOP_V1.md`, `OCR_AND_VERIFY.md` | фрагментированная v1-документация, частичный дубль | `../README.md`, `../docs/API.md`, `../docs/ARCHITECTURE.md`, `../docs/CONFIG.md` |
| `INTENT_ROUTER.md`, `SEMANTIC_BRAIN.md`, `BRAIN_LAYER.md`, `PRIVACY_AND_ROUTING.md`, `SAFETY_AND_APPROVALS.md`, `SKILLS.md`, `CONTRACTS.md` | пересечения по терминам и потокам, единый источник отсутствовал | `../docs/ARCHITECTURE.md`, `../docs/SECURITY.md`, `../docs/API.md` |
| `README_PERSONAL.md` | персональная заметка, не публичная эксплуатационная дока | `../README.md` |

Если нужна ретроспектива старых формулировок — используйте файлы в этой папке или git history.
