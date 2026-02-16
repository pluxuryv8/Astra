# AUDIT_LLM_MEMORY_WEB_FEEDBACK

## 1. LLM routing & defaults
Brain routing is centralized in `BrainRouter`, which chooses local vs cloud, builds messages, and selects models based on route and `preferred_model_kind`. (`core/brain/router.py:105-205`, `core/brain/router.py:249-333`, `core/brain/router.py:480-497`, `core/brain/types.py:9-19`)

**Config/env defaults**

| config/env | meaning | evidence |
| --- | --- | --- |
| `ASTRA_LLM_LOCAL_BASE_URL` (default `http://127.0.0.1:11434`) | Base URL for local LLM (Ollama) | `core/brain/router.py:66-66` |
| `ASTRA_LLM_LOCAL_CHAT_MODEL` (default `saiga-nemo-12b`) | Default local chat model | `core/brain/router.py:67-67` |
| `ASTRA_LLM_LOCAL_CODE_MODEL` (default `deepseek-coder-v2:16b-lite-instruct-q8_0`) | Default local code model | `core/brain/router.py:68-68` |
| `ASTRA_LLM_CLOUD_BASE_URL` (default `https://api.openai.com/v1`) | Cloud base URL | `core/brain/router.py:69-69` |
| `ASTRA_LLM_CLOUD_MODEL` (default `gpt-4.1`) | Default cloud model | `core/brain/router.py:70-70` |
| `ASTRA_CLOUD_ENABLED` (default `false`, forced `false` if no `OPENAI_API_KEY`) | Cloud enable flag | `core/brain/router.py:60-63` |
| `ASTRA_AUTO_CLOUD_ENABLED` (default `false`) | Auto-cloud switching enable flag | `core/brain/router.py:72-72` |
| `ASTRA_LLM_MAX_CONCURRENCY` (default `1`) | LLM concurrency limit | `core/brain/router.py:73-73` |
| `ASTRA_LLM_MAX_RETRIES` (default `3`) | Cloud retry count | `core/brain/router.py:74-74` |
| `ASTRA_LLM_BACKOFF_BASE_MS` (default `350`) | Backoff base for cloud retries | `core/brain/router.py:75-75` |
| `ASTRA_LLM_BUDGET_PER_RUN` (default `None`) | Budget per run | `core/brain/router.py:76-76` |
| `ASTRA_LLM_BUDGET_PER_STEP` (default `None`) | Budget per step | `core/brain/router.py:77-77` |
| `OPENAI_API_KEY` | Cloud auth; missing key disables cloud and causes cloud call to error | `core/brain/router.py:60-63`, `core/brain/router.py:405-408` |

**Routing logic and auto-cloud triggers**
- Policy flags are loaded from a `settings` dict using `privacy`/`routing` keys (auto-cloud, cloud-allowed, strict-local). (`core/llm_routing.py:64-71`)
- `decide_route` forces LOCAL for `strict_local` or `telegram_text`, and routes to CLOUD for web page text or heavy public text when auto-cloud and cloud-allowed are true. (`core/llm_routing.py:250-287`)
- `BrainRouter` can override with auto-switch reasons like `heavy_writing`, `web_page_text_long`, `local_failures`, `code_local_failures`. (`core/brain/router.py:499-517`)
- `ASTRA_CLOUD_ENABLED` / `ASTRA_AUTO_CLOUD_ENABLED` env vars override policy flags at runtime when set. (`core/brain/router.py:168-173`)
- Project creation defaults to `llm.provider=openai`, `base_url=https://api.openai.com/v1`, `model=gpt-4.1` if settings are missing. (`apps/api/routes/projects.py:12-23`)
- Cloud model/base URL can be overridden from `ctx.settings` via `llm_cloud` or `llm` inside `_select_model`. (`core/brain/router.py:491-497`)
- Chat run context passes `project.get(\"settings\")` into `ctx.settings` for LLM calls. (`apps/api/routes/runs.py:207-207`)

**Chat vs code model selection**
- `LLMRequest.preferred_model_kind` defaults to `"chat"`. (`core/brain/types.py:16-16`)
- `BrainRouter._select_model` returns local code model when `kind == "code"`, otherwise local chat model. (`core/brain/router.py:487-490`)
- `LocalLLMProvider` picks `code_model` vs `chat_model` using `model_kind`. (`core/brain/providers.py:130-144`)

**Provider endpoints**
- Local LLM calls POST `{local_base_url}/api/chat`. (`core/brain/providers.py:162-166`)
- Cloud LLM calls POST `{cloud_base_url}/chat/completions` with `Authorization: Bearer`. (`core/brain/providers.py:300-307`)


**Runtime scripts (env/runtime context)**  
- `scripts/run.sh` loads `.env`, sets `ASTRA_API_PORT`, and defaults `ASTRA_DATA_DIR` to `.astra`. (`scripts/run.sh:12-71`)  
- `scripts/astra` defines `OLLAMA_PORT=11434`, starts Ollama if needed, and calls `./scripts/run.sh --background`. (`scripts/astra:13-108`)  

## 2. Prompt/message construction
`BrainRouter` builds the final message list using either `LLMRequest.render_messages` or `LLMRequest.messages`, otherwise it raises. (`core/brain/router.py:480-485`, `core/brain/types.py:14-16`)

**Known LLM call sites and templates**
- Chat response (API): system + user messages are created inline; name hint is appended to system content. (`apps/api/routes/runs.py:208-229`, `apps/api/routes/runs.py:213-231`)
- Planner LLM: system + user messages built in `_llm_plan`, then used in `LLMRequest`. (`core/planner.py:691-719`)
- Intent router LLM: system + user messages built in `_llm_classify`, then used in `LLMRequest`. (`core/intent_router.py:490-514`)
- Autopilot micro-planner: `render_messages` builds system + user (JSON payload) for `computer_micro_plan`. (`core/executor/computer_executor.py:474-512`)
- Clarify phrase constants are defined in `core/assistant_phrases.py` and imported by the intent router. (`core/assistant_phrases.py:5-7`, `core/intent_router.py:9-12`)

**Message normalization / payload shape**
- Local provider normalizes each message to `{role, content}` strings. (`core/brain/providers.py:35-46`, `core/brain/providers.py:145-148`)
- Cloud provider forwards `messages` as provided. (`core/brain/providers.py:288-291`)
- UI fallback phrases for chat/clarify are defined in `assistantPhrases.ts` and used when `chat_response` is missing. (`apps/desktop/src/shared/assistantPhrases.ts:1-8`, `apps/desktop/src/shared/store/appStore.ts:1237-1245`)

**Injection points for history/preferences (audit-only)**
- Chat history/preferences can be inserted into the `messages` array in `create_run` before `LLMRequest` is sent. (`apps/api/routes/runs.py:213-231`)
- For planning and intent routing, history/preferences can be inserted into the `messages` arrays built in `_llm_plan` and `_llm_classify`. (`core/planner.py:691-719`, `core/intent_router.py:490-514`)
- For autopilot micro-plans, history/preferences can be injected inside `render_messages`. (`core/executor/computer_executor.py:474-512`)

## 3. Conversation history
**Current persistence**
- UI conversation messages are stored in localStorage under `astra.ui.conversationMessages` and loaded on startup. (`apps/desktop/src/shared/store/appStore.ts:59-60`, `apps/desktop/src/shared/store/appStore.ts:347-349`)
- Messages are saved with a debounce and capped at `MESSAGE_LIMIT = 240`. (`apps/desktop/src/shared/store/appStore.ts:359-367`, `apps/desktop/src/shared/store/appStore.ts:400-402`)
- Message shape includes `id`, `chat_id`, `role`, `text`, `ts`, `run_id?`. (`apps/desktop/src/shared/types/ui.ts:11-18`)
- Chat responses are appended from API `chat_response` into conversation messages. (`apps/desktop/src/shared/store/appStore.ts:1243-1252`)

**Server-side data**
- DB schema includes `runs` (stores `query_text`) and `events`, but no chat messages table is defined. (`memory/migrations/001_init.sql:19-112`)
- `chat_response_generated` event schema includes provider/model/latency only (no response text). (`schemas/events/chat_response_generated.schema.json:6-12`)
- SSE stream is `/api/v1/runs/{run_id}/events` and emits DB events only. (`apps/api/routes/run_events.py:15-49`, `memory/store.py:1289-1308`)
- The API returns `chat_response` directly in response, not stored in DB. (`apps/api/routes/runs.py:242-242`)

**Negative search evidence**
- Command: `rg -n "messages|conversation" randarc-astra/memory/migrations` → no matches (no conversation/messages table in migrations). (command output: no matches)

**Proposed insertion points (audit-only, no changes)**
- Add a chat-messages table migration near `memory/migrations/001_init.sql`. (`memory/migrations/001_init.sql:19-112`)
- Add `store.insert_chat_message` / `list_chat_messages` in `memory/store.py` alongside event helpers. (`memory/store.py:1245-1324`)
- Persist user+assistant turns when `create_run` builds chat messages. (`apps/api/routes/runs.py:213-242`)
- If UI should load history from API, add an API client method similar to `listRuns` and update `appStore` to hydrate `conversationMessages`. (`apps/desktop/src/shared/api/client.ts:81-90`, `apps/desktop/src/shared/store/appStore.ts:347-365`)

## 4. User memory
**Storage**
- User memories are stored in table `user_memories` with fields `title`, `content`, `tags`, `source`, `pinned`, `last_used_at`. (`memory/migrations/006_user_memories.sql:1-12`)
- Content length limit is controlled by `ASTRA_MEMORY_MAX_CHARS` (default 4000). (`memory/store.py:59-67`)
- `create_user_memory` inserts into `user_memories` and returns a dict. (`memory/store.py:1098-1147`)
- `list_user_memories` reads from `user_memories` with filters. (`memory/store.py:1151-1177`)

**Write paths**
- `memory_save` skill writes user memory and emits `memory_save_requested` / `memory_saved`. (`skills/memory_save/skill.py:8-35`)
- API endpoints list/create/delete memory and emit the same events. (`apps/api/routes/memory.py:19-77`)
- Memory-related event schemas exist for `memory_save_requested`, `memory_saved`, `memory_list_viewed`, `memory_deleted`. (`schemas/events/memory_save_requested.schema.json:1-11`, `schemas/events/memory_saved.schema.json:1-13`, `schemas/events/memory_list_viewed.schema.json:1-11`, `schemas/events/memory_deleted.schema.json:1-10`)
- Planner kind `KIND_MEMORY_COMMIT` maps to skill `memory_save`, and `_append_memory_step_if_needed` adds that step when memory triggers match. (`core/planner.py:21-49`, `core/planner.py:819-834`)

**Read/injection into prompts**
- `_resolve_user_name` looks up `list_user_memories(query="меня зовут")` and extracts a name. (`apps/api/routes/runs.py:39-52`)
- The resolved name is injected into chat system prompt via `name_hint`. (`apps/api/routes/runs.py:208-229`)
- This is the only `list_user_memories` call site in the repo. (command: `rg -n "list_user_memories" randarc-astra` → hits only `apps/api/routes/runs.py` and `apps/api/routes/memory.py`)

## 5. Web research
**UI/browser flow (planner)**
- Planner kinds include `KIND_BROWSER_RESEARCH`, mapped to skill `autopilot_computer`. (`core/planner.py:18-49`)
- `_plan_browser_research` creates steps to open browser and find sources. (`core/planner.py:483-518`)

**API search flow (web_research skill)**
- `web_research` skill calls `build_search_client` and converts results into `SourceCandidate`s. (`skills/web_research/skill.py:16-48`)
- `build_search_client` uses Yandex API when `provider == "yandex"` and requires `YANDEX_API_KEY` + `search_url`; otherwise it falls back to `StubSearchClient`. (`core/providers/search_client.py:54-65`)
- Skill registry and manifest declare provider `yandex`. (`skills/registry/registry.json:51-65`, `skills/web_research/manifest.json:1-9`)

**Reference coverage**
- `web_research` is only referenced in registry/manifest; no planner or runtime use found. (command: `rg -n "web_research" randarc-astra/core randarc-astra/skills randarc-astra/apps` → hits only registry/manifest)

**Change points for browser-only research (audit-only)**
- If `web_research` is used, disable Yandex API by changing `build_search_client` to always return `StubSearchClient` (or a browser-based client). (`core/providers/search_client.py:54-65`)
- Keep browser research via planner steps (autopilot UI) by relying on `KIND_BROWSER_RESEARCH` → `autopilot_computer`. (`core/planner.py:18-49`, `core/planner.py:483-518`)

## 6. Feedback loop (audit-only plan)
**Existing UI feedback (local only)**
- Chat UI renders thumbs up/down per message and invokes handlers. (`apps/desktop/src/widgets/ChatThread.tsx:10-85`)
- Feedback is stored in localStorage key `preference_feedback` with message id, rating, optional text. (`apps/desktop/src/pages/ChatPage.tsx:16-51`, `apps/desktop/src/pages/ChatPage.tsx:173-217`)
- No API routes for feedback were found. (command: `rg -n "feedback" randarc-astra/apps/api/routes` → no matches)

**Event system touchpoints (for minimal server integration)**
- Event types are loaded from `schemas/events/*.schema.json` and enforced by `core/event_bus.emit`. (`core/event_bus.py:48-78`)
- Events are stored in DB table `events`. (`memory/migrations/001_init.sql:101-111`, `memory/store.py:1245-1263`)
- UI subscribes to a fixed list of event types and uses SSE `EventSource` for `/runs/{run_id}/events`. (`apps/desktop/src/shared/store/appStore.ts:73-129`, `apps/desktop/src/shared/api/eventStream.ts:37-183`, `apps/api/routes/run_events.py:15-49`)

**Minimal integration points (audit-only, no changes)**
- UI: add API call from `handleThumbUp`/`submitFeedback` in `ChatPage` (or via `appStore`) to send `message_id`, `rating`, `text`. (`apps/desktop/src/pages/ChatPage.tsx:173-217`, `apps/desktop/src/shared/store/appStore.ts:1201-1264`)
- UI/API auth: API client attaches `Authorization: Bearer` using token from `authController` localStorage. (`apps/desktop/src/shared/api/client.ts:21-38`, `apps/desktop/src/shared/api/authController.ts:4-40`)
- API: add a feedback route (e.g., under `/api/v1/runs/...`) and emit an event via `core.event_bus.emit`. (`apps/api/routes/runs.py:121-242`, `core/event_bus.py:68-78`)
- Auth status endpoint returns `auth_mode` and `token_required`. (`apps/api/routes/auth.py:13-21`)
- DB: store feedback as a new event type (new schema in `schemas/events/`) or add a dedicated table migration. (`schemas/event.schema.json:1-123`, `memory/migrations/001_init.sql:101-111`)
- Prompt injection: aggregate feedback and prepend to chat `messages` in `create_run` or `render_messages` sites. (`apps/api/routes/runs.py:213-231`, `core/executor/computer_executor.py:474-512`)

## 7. Unknowns
- **НЕИЗВЕСТНО:** actual runtime values of LLM env vars (enabled cloud, models, base URLs). Confirm by running `./scripts/doctor.sh prereq` and inspecting env output. (`scripts/doctor.sh:54-64`)
- **НЕИЗВЕСТНО:** whether required local models are installed in Ollama at runtime. Confirm by running `curl $ASTRA_LLM_LOCAL_BASE_URL/api/tags` or the doctor check. (`scripts/doctor.sh:92-121`)
