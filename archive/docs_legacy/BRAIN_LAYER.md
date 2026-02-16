# Brain Layer

## Overview
The Brain layer provides a single entry point for all LLM calls. It enforces privacy routing (LOCAL/CLOUD), sanitization, budgeting, caching, and audit events.

Implementation:
- Router + queue + cache + budgets: `core/brain/router.py`
- Providers: `core/brain/providers.py`
- Request/response types: `core/brain/types.py`
- Policy + sanitizer: `core/llm_routing.py`

## Call Flow
1. Build `LLMRequest` with `context_items` and `render_messages`.
2. BrainRouter:
   - applies policy (see `docs/PRIVACY_AND_ROUTING.md`),
   - performs sanitization for CLOUD,
   - selects provider + model,
   - runs through queue (concurrency=1 by default),
   - emits audit events,
   - returns `LLMResponse`.

## Auto-switch (simple rules)
- Default: LOCAL.
- Switch to CLOUD when:
  - `task_kind` is `heavy_writing` / `long_form` / `report` and all context is `public`.
  - Context contains only `web_page_text` and is long (>= ~1200 chars).
  - Local failures reach threshold (2 for chat, 1+ for code).
- Any CLOUD route must pass PolicyEngine (telegram => LOCAL, financial file => approval).

## Privacy & Routing
See `docs/PRIVACY_AND_ROUTING.md` for source-type rules and approval requirements.

## Audit Events
Events emitted by BrainRouter:
- `llm_route_decided`
- `llm_request_sanitized`
- `llm_request_started`
- `llm_request_succeeded`
- `llm_request_failed`
- `llm_budget_exceeded`

## Troubleshooting
- Local Ollama:
  - `curl http://127.0.0.1:11434/api/tags`
  - `./scripts/doctor.sh` (checks Ollama health + required models)
- Cloud:
  - Ensure `OPENAI_API_KEY` is set when `ASTRA_CLOUD_ENABLED=true`.

## Example Usage
Call sites should create a request and call the Brain:
- `skills/extract_facts/skill.py`
- `skills/autopilot_computer/skill.py`
