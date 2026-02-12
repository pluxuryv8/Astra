# Privacy & Routing Policy (Local vs Cloud)

## Rules (A–F)
- Default route is LOCAL.
- CLOUD can be used automatically for:
  - heavy, public, general-purpose text (for example, long public reports/articles),
  - text extracted from public web pages.
- Telegram/chat content is always LOCAL.
- Financial file content can go to CLOUD only with explicit per-step approval.
- Auto-cloud decisions must be logged with a reason in run events.
- Mixed context with any forbidden source (for example, web + telegram) forces LOCAL.

## Source Type Matrix
- `user_prompt`: LOCAL by default. CLOUD only if marked `public` and long (heavy public text).
- `web_page_text`: CLOUD allowed without approval.
- `telegram_text`: LOCAL only (never CLOUD).
- `file_content`: LOCAL by default. `financial` requires approval to go CLOUD.
- `app_ui_text`: LOCAL only.
- `screenshot_text`: LOCAL only.
- `system_note`: LOCAL by default. CLOUD only if `public` and heavy.
- `internal_summary`: LOCAL by default. CLOUD only if `public` and heavy.

## Examples
- Web research snippets only → CLOUD allowed.
- Telegram message present → LOCAL only.
- Financial file without approval → LOCAL (approval required for CLOUD).
- Mixed web + telegram → LOCAL.

## Audit Events
- `llm_route_decided` (final route + reason)
- `llm_request_sanitized` (removed sources + truncation)
- `llm_request_started` (provider + model)
- `llm_request_succeeded` (latency + cache_hit)
- `llm_request_failed` (error + http status)
- `llm_budget_exceeded` (budget name + limit + current)

## Implementation Locations
- Policy + sanitizer + approvals + routing: `core/llm_routing.py`
- Brain router (queue, provider selection, audit events): `core/brain/router.py`
- LLM usage with policy:
  - `skills/extract_facts/skill.py`
  - `skills/autopilot_computer/skill.py`
- Event schemas:
  - `schemas/events/llm_route_decided.schema.json`
  - `schemas/events/llm_request_sanitized.schema.json`
  - `schemas/events/llm_request_started.schema.json`
  - `schemas/events/llm_request_succeeded.schema.json`
  - `schemas/events/llm_request_failed.schema.json`
  - `schemas/events/llm_budget_exceeded.schema.json`
- Tests:
  - `tests/test_privacy_routing.py`

## Settings (Project Settings)
- `privacy.auto_cloud_enabled` (bool)
- `privacy.cloud_allowed` (bool)
- `privacy.strict_local` (bool)
- `privacy.max_cloud_chars` (int)
- `privacy.max_cloud_item_chars` (int)

Notes:
- LOCAL route requires a local OpenAI-compatible endpoint (`llm_local` or `llm` with a localhost base URL).
- CLOUD route uses `llm_cloud` or falls back to `llm`.
