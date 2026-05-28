ADK Spanish Hotel Reservation Voice Assistant
============================================

**Author:** Andres Lage  
**Copyright:** © 2026 Andres Lage (MIT License — see [LICENSE](LICENSE)).

This project provides a **Spanish-speaking hotel reservation assistant** that can run
as a voice-first kiosk, a CLI/chatbot, and a small Flask-based webhook service.
It is powered by **Google Gemini 3.5 Flash** (default: `gemini-3.5-flash`; set
`GEMINI_MODEL=gemini-2.0-flash` in `.env` for a lower-cost alternative)
and is designed for lightweight production deployments.

Features
--------
- Voice and text interaction loops with smooth runtime switching.
- Gemini-powered NLU with conversation memory, **structured intent + entity extraction**
  (JSON schema by default; optional **function-calling** routing via `USE_INTENT_FUNCTION_CALLING=true`),
  and keyword fallback when routing is disabled or fails.
- **Session storage**: in-memory for a single process, or **Redis** (`REDIS_URL`) for Waitress
  multi-worker / horizontal scaling (TTL aligned with `SESSION_TIMEOUT_MINUTES`).
- Flask **application factory** (`create_app`) with dependencies on **`flask.g`** per request
  (no module-level agent references inside route handlers).
- Webhook endpoints (`/webhook/trigger`, `/webhook/booking_event`, `/health`) and pluggable
  booking callbacks; booking payloads include `current_reservation` and `extracted_entities`
  when available.
- **Web demo UI** at `/demo/` — chat layout optimized for **screen recording** (large type,
  high contrast, **light/dark** follows OS preference). Renders assistant replies as **Markdown**
  (via `marked` + `DOMPurify` in the browser), **textarea** with auto-resize, **typing indicator**,
  optional **mic** (records locally, transcribes via **`/webhook/transcribe`** + Gemini — no Chrome cloud STT).
  Open while the webhook server is running,
  set `WEBHOOK_API_KEY` if needed. **Rate limiting** on `/webhook/trigger`
  (`WEBHOOK_RATE_LIMIT_PER_MINUTE`, default 60/min per IP).

Quick start
-----------
1. **Create and activate a virtual environment** (recommended).
2. **Install dependencies** (runtime only, or dev + tests + PDF generation):

```bash
pip install -r requirements.txt
# optional: tests and scripts/generate_assistant_doc.py
pip install -r requirements-dev.txt
```

3. **Set your Google Gemini API key** (never commit the real value):
- Option A – environment variable (recommended):

- Linux/macOS:

```bash
export GOOGLE_API_KEY="YOUR_KEY_HERE"
```

- Windows PowerShell:

```powershell
$env:GOOGLE_API_KEY="YOUR_KEY_HERE"
```

- Option B – `.env` file (for local dev only, **do not commit**):

Create a copy of `.env.example` named `.env` and fill in the values. The
`.gitignore` file is configured so `.env` stays out of version control.

4. **Run the assistant in text (CLI) mode** (from the project root):

```bash
python -m adk_spanish_hotel_voice_assistant --mode code
```

5. **Run the webhook server**:

```bash
python -m adk_spanish_hotel_voice_assistant --serve-webhook
```

6. **Open the demo UI** (with `GOOGLE_API_KEY` set so the agent loads):

Visit **`http://127.0.0.1:8080/demo/`** (or your `HOST`/`PORT`). Use a maximized window for clean **video demos** (OBS, Game Bar, or OS capture).

The `/webhook/trigger` response includes a `session_id` that always matches the
conversation store; send it back on the next request to continue the same session.

Security (OWASP Agentic Top 10, 2026 alignment)
------------------------------------------------
This assistant is designed with **OWASP Top 10 for Agentic Applications (2026)** in mind
(GenAI Security Project; see [genai.owasp.org](https://genai.owasp.org)). Highlights:

- **ASI01 / ASI06 (goal hijack, context poisoning):** Hardened Spanish system prompt; bounded
  chat history; strict **UUID v4** validation for `session_id` on webhooks and `/session/<id>`.
- **ASI02 (tool misuse):** Routing uses a **single structured schema / tool** with enumerated
  intents; booking hooks do not execute user-supplied code.
- **ASI03 (identity / privilege):** Optional **`WEBHOOK_API_KEY`** (`X-Webhook-Key` or
  `Authorization: Bearer`) for webhook POST routes; optional **`SESSION_API_KEY`** for session
  inspection; secrets compared with **SHA-256 + constant-time** `hmac.compare_digest`.
- **ASI05 (RCE):** No `eval` on user text; typed JSON fields; **`MAX_REQUEST_BYTES`** limits
  body size (Flask `MAX_CONTENT_LENGTH`).
- **ASI07 / ASI08 / ASI09:** Use **HTTPS** in production; generic **5xx** payloads; external
  booking calls use **timeouts**; stack traces stay in logs, not API responses.

Generated PDF documentation includes a **dedicated OWASP mapping section** with CC BY-SA 4.0
attribution. Run `python scripts/generate_assistant_doc.py` to refresh `docs/hotel_voice_assistant_overview.pdf`.

Guardrails and safety
---------------------
- The `/webhook/trigger` and `/webhook/booking_event` endpoints validate that:
  - The request body is valid JSON.
  - The payload is a JSON object (not an array or other type).
  - Key fields (such as `text` and `session_id`) have the expected types.
- When something goes wrong server-side, the API returns a **generic 500‑level error
  message** instead of exposing internal stack traces.
- `GOOGLE_API_KEY` is required; the entry point prints OS‑specific examples for
  setting it correctly.

Testing
-------
Run the test suite with:

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover:
- `GeminiAgent` context handling and intent callbacks.
- Session expiration via `SessionManager.cleanup_expired_sessions`.
- Flask `create_app` wiring and `/health` + `/webhook/trigger` with a stub agent.

Real hotel prices (Amadeus GDS)
-------------------------------
Without Amadeus credentials the assistant may **simulate** bookings (`booking.py`).
For **live availability and prices**:

1. Create a free app at [Amadeus for Developers](https://developers.amadeus.com/).
2. Copy **API Key** and **API Secret** into `.env` as `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`.
3. Keep `AMADEUS_API_HOST=https://test.api.amadeus.com` for sandbox data (limited hotels).
4. Restart the webhook server. `/health` should show `"amadeus_hotel_search": true`.

The Gemini agent exposes the tool **`buscar_disponibilidad_hotel(ciudad, check_in, check_out)`**
(calls `GET /v3/shopping/hotel-offers`). When the user asks for rates, the model fetches real JSON
and must quote those prices—not invented amounts.

Extending the assistant
------------------------
- Implement your own booking integration by overriding
  `callbacks.on_booking_request` with a function that calls your hotel API.
- Use `callbacks.on_intent` for analytics, logging, or routing to human agents.
- Use the `/session/<session_id>` endpoint to inspect conversation metadata for
  audits or debugging (set `SESSION_API_KEY` in production and send `X-API-Key`).
- Set `WEBHOOK_API_KEY` so only your frontends or integration layer can call webhook POST routes.
- Behind nginx/ingress set `TRUSTED_PROXY_HOPS=1` so **ProxyFix** rewrites `request.remote_addr` for rate limiting (`/health` reports `proxy_fix_active: true`).

Repository layout
-----------------
- `adk_spanish_hotel_voice_assistant/` — Python package (agent, Flask factory, sessions, routing).
- `tests/` — `pytest` suite (no live Gemini calls required).
- `scripts/generate_assistant_doc.py` — regenerates `docs/hotel_voice_assistant_overview.pdf`.
- `docs/architecture.html` — **diagramas Mermaid** (componentes, webhook, routing). Con el servidor webhook: **`http://127.0.0.1:8080/docs/architecture`**; también se puede abrir el HTML localmente en el navegador.
- `.env.example` — copy to `.env` for local secrets (never commit `.env`).

Publishing to GitHub
--------------------
1. Create an empty repository on GitHub (no README/license if you already have them here).
2. From this folder:

```bash
git init
git add .
git commit -m "Initial commit: Spanish hotel voice assistant"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

Use a repository path **without spaces** on disk if you can (e.g. `booking-voice`); spaces work but are awkward in shells.

License
-------
Copyright (c) 2026 **Andres Lage**. This project is licensed under the [MIT License](LICENSE). Documentation in `docs/` may cite third-party standards (e.g. OWASP) under their respective licenses; see the PDF attribution section where applicable.

