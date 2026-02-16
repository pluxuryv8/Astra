# Overlay v1

## Что делает
- Маленькое окно поверх всех (always-on-top) со статусом run.
- Кнопки Stop / Pause-Resume / Open.
- Сигнализирует о pending approvals.

## Как включить
- Overlay окно создаётся через команду Tauri `overlay_show`.
- Горячая клавиша: `Cmd+Shift+O` (toggle).

## Режимы
- `auto`: показывается, когда run активен или есть approval.
- `pinned`: всегда показывается.
- `off`: скрыт.

Хранение режима: `localStorage` ключ `astra_overlay_mode`.

## Где реализовано
- Окно overlay и команды: `apps/desktop/src-tauri/src/main.rs`.
- UI overlay: `apps/desktop/src/OverlayApp.tsx`.
- Статусы/маппинг: `apps/desktop/src/ui/overlay_utils.ts`.
- Управление показом из main UI: `apps/desktop/src/MainApp.tsx`.

## Дебаг
- Если overlay не появляется: проверь `overlay_show`/`overlay_hide` в логах Tauri.
- Если нет статуса: проверь `localStorage` ключ `astra_last_run_id` и SSE `/runs/{id}/events`.
