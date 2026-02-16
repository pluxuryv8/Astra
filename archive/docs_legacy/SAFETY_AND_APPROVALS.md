# SAFETY_AND_APPROVALS v1

## Опасные категории (A–E)
- SEND: отправка сообщения/поста/комментария
- DELETE: удаление/безвозвратные изменения
- PAYMENT: оплата/перевод/подписка
- PUBLISH: публикация контента
- ACCOUNT_CHANGE: изменения аккаунта/безопасности + ввод пароля
- CLOUD_FINANCIAL: отправка финансовых данных в облако

## Approval Contract (preview)
Каждый approval содержит:
- `approval_type`: SEND | DELETE | PAYMENT | PUBLISH | ACCOUNT_CHANGE | CLOUD_FINANCIAL
- `preview`:
  - `summary`
  - `details`
  - `risk`
  - `suggested_user_action`
  - `expires_in_ms`

Preview хранится в БД (колонка `preview_json`). В события попадает только `preview_summary`.

## Где стоит safety‑gate
- Executor Loop: `core/executor/computer_executor.py`
  - до выполнения шага с `danger_flags` / `requires_approval`
  - пароль/код: `user_action_required` + approval
- LLM routing (финансовые файлы): `core/llm_routing.py`
- Skills confirm gate: `core/skills/runner.py`

## Пароли/коды
Astra не вводит пароли. При `danger_flags` = `password`:
- эмитится `user_action_required`
- создаётся approval
- шаг завершится после подтверждения пользователя

## События
- `approval_requested` (approval_type, preview_summary, step_id)
- `approval_resolved`
- `step_paused_for_approval`
- `step_cancelled_by_user`
- `user_action_required`

## Примеры preview
SEND:
```json
{
  "summary": "Отправить сообщение",
  "details": {
    "target_app": "Telegram",
    "message_text": "Привет!",
    "destination_hint": "UNKNOWN"
  },
  "risk": "Отправка сообщения/публикация",
  "suggested_user_action": "Проверьте получателя и текст сообщения",
  "expires_in_ms": null
}
```

DELETE:
```json
{
  "summary": "Удалить файлы",
  "details": {
    "items": "UNKNOWN",
    "impact": "UNKNOWN"
  },
  "risk": "Удаление или необратимое изменение",
  "suggested_user_action": "Подтвердите список удаляемых объектов",
  "expires_in_ms": null
}
```

CLOUD_FINANCIAL:
```json
{
  "summary": "Отправка финансовых данных в облако",
  "details": {
    "file_paths": ["/path/to/file.xlsx"],
    "content": "выжимка/фрагменты",
    "redaction_summary": {"file_content": 0}
  },
  "risk": "Передача финансовых данных в облако",
  "suggested_user_action": "Подтвердите отправку финансовых данных в облако",
  "expires_in_ms": null
}
```

## Как дебажить
- смотрите SSE‑события: `approval_requested`, `step_paused_for_approval`, `approval_resolved`, `step_cancelled_by_user`
- проверяйте approval запись через API: `GET /api/v1/runs/{run_id}/approvals`
