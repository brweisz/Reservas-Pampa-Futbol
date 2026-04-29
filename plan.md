# Plan: Pampa Futbol Booking Bot as a Web Service

## Goal

Turn the current single-user CLI bot into a self-serve web app:
1. User opens a webpage.
2. Enters their Pampa Futbol credentials (DOCUMENTO + PASSWORD) and a notification email.
3. Picks a class from a list scraped live from pampafutbol.com.
4. Backend polls until the class opens, books it, sends a confirmation email.

Constraint: free-tier hosting only. No credentials persisted to disk.

**Email model:**
- Sender is fixed: `botpampafutbol@gmail.com` (the bot's own Gmail account, configured server-side via `MAIL_FROM` + `MAIL_PASSWORD` env vars — Gmail App Password).
- Recipient is supplied by the user per request (replaces today's `MAIL_TO` env var).

---

## Stack

- **Frontend:** React + Vite, deployed as a static SPA on **Cloudflare Pages** (free, no card).
- **Backend:** Python + FastAPI on **Oracle Cloud Always Free** (ARM VM, 4 cores / 24GB RAM). Reuses existing Playwright code.
- **Job model:** in-process `asyncio` task per booking job. No external queue, no DB.
- **DB:** none. All state (job records, Playwright contexts, user emails) lives in a Python dict keyed by job id, in process memory.
- **Email:** existing `notificacion.py` over Gmail SMTP, with the recipient taken from the job record.
- **Reverse proxy / TLS:** Caddy or Nginx + Let's Encrypt on the Oracle VM.

---

## Hosting: Oracle Cloud Always Free

- Provision a 1× Ampere A1 ARM VM (up to 4 OCPU / 24GB RAM, free forever).
- Install Docker + the project's Playwright image; run the FastAPI container.
- Open ports 80/443 in the VCN security list and on the host firewall (`firewalld` / `iptables`).
- Point a domain (or a free `*.duckdns.org` / `*.nip.io` host) at the VM's public IP.
- Caddy auto-provisions HTTPS.
- **Note:** Oracle Cloud signup requires a credit/debit card for identity verification (auth charge, refunded). Once signed up, Always Free resources never bill.

---

## Architecture

```
[ Browser: React SPA on Cloudflare Pages ]
              │  HTTPS (fetch)
              ▼
[ FastAPI on Oracle VM, behind Caddy/HTTPS ]
              │
              ├── in-memory JOB_REGISTRY: { job_id → JobRecord }
              │     JobRecord = {
              │       playwright_context,   # holds session cookie
              │       email,                # notification recipient
              │       chosen_class | None,
              │       status,               # waiting | polling | booked | failed
              │       task: asyncio.Task | None,
              │     }
              │
              └── per-job asyncio.Task running the poll loop
                   └── on success → notificacion.enviar_notificacion(record.email)
                                  → tear down Playwright context
                                  → drop record from registry
```

### Request flow

1. **`POST /login`** — body: `{ documento, password, email }`
   - Server starts a Playwright Chromium context, logs in at `/login`, waits for redirect to `/`.
   - Server scrapes `/alumno/clases-disponibles` once, returns the class list.
   - Server creates a `JobRecord` with the live Playwright context + email, generates a `job_id` (UUID), stores it in `JOB_REGISTRY`.
   - **Plaintext `documento` and `password` are dropped immediately after login succeeds. They are never stored in the record, logged, or returned.**
   - Response: `{ job_id, classes: [{ index, fecha, nivel, sede, disponible }, ...] }`.

2. **`POST /book`** — body: `{ job_id, class_tuple: { fecha, nivel, sede } }`
   - Server looks up the record, sets `chosen_class`, spawns an `asyncio.Task` running the poll loop.
   - Poll loop: every `INTERVALO_SEGUNDOS` (30s), reload the page, re-scrape, find the matching `(fecha, nivel, sede)` tuple, click the chip if `aria-disabled` is false.
   - On booking success: send email to `record.email`, set status to `booked`, close the Playwright context, remove the record from the registry.
   - On unrecoverable error: set status to `failed`, send a failure email, clean up.
   - Response: `{ status: "polling" }`.

3. **`GET /status/{job_id}`** — returns `{ status, last_checked_at }`. Frontend can poll this for live UI feedback; email remains the source of truth.

4. **`DELETE /job/{job_id}`** — user cancels. Cancels the asyncio task, closes the Playwright context, drops the record.

### Concurrency model

- One `asyncio.Task` per active job, all sharing a single Playwright instance (one browser, many contexts).
- Each context = isolated cookies = one logged-in user.
- Memory budget: ~80–150MB per active context. On a 24GB Oracle VM this comfortably handles dozens of simultaneous users; the practical bottleneck is Pampa's servers, not ours.
- A janitor task scans `JOB_REGISTRY` every few minutes and evicts records older than a TTL (e.g. 6 hours) to prevent leaks from abandoned jobs.

### Lifecycle of an in-memory record

| Event | Effect on JobRecord |
|---|---|
| `POST /login` succeeds | record created, credentials dropped, context kept |
| `POST /book` | `chosen_class` set, polling task started |
| Booking succeeds | email sent, context closed, record deleted |
| Booking fails terminally | failure email sent, context closed, record deleted |
| User calls `DELETE /job` | task cancelled, context closed, record deleted |
| TTL expires | task cancelled, context closed, record deleted |
| **Server restart** | **all records lost — user must restart from `/login`** |

---

## Credential management

**In-memory only — no DB persistence of credentials.**

- Credentials arrive over HTTPS, used immediately to log in via Playwright.
- After login succeeds, plaintext credentials are dropped from local variables and never copied into the `JobRecord`.
- The Playwright browser context (holding the session cookie) stays alive in memory for the polling job's lifetime — that cookie is the only thing needed for subsequent reloads.
- If the server restarts mid-job, the session is lost and the user must re-enter credentials.
- The user's notification email lives in the in-memory job record only; it is discarded when the record is removed.

**Never:**
- Log credentials.
- Return credentials to the frontend after submission.
- Persist credentials to disk or DB in any form.

---

## Refactor of existing code

`bot.py` becomes a library, not an entry point:

- `async def login(documento, password) -> BrowserContext` — opens a context, logs in, returns it.
- `async def list_classes(context) -> list[Class]` — scrapes the listing once.
- `async def poll_and_book(context, class_tuple, on_success) -> None` — the existing poll loop, callback-driven.

A new `app/main.py` (FastAPI) wraps these in the endpoints above and manages `JOB_REGISTRY`.

`notificacion.py` keeps its current shape; the call site passes `to=record.email` instead of reading `MAIL_TO`.

---

## Risks

- **Selector breakage** — same as today; documented in CLAUDE.md.
- **Gmail SMTP rate limits** — fine at low volume; if usage grows, swap to Resend / Brevo free tier.
- **Server restart loses jobs** — accepted tradeoff for the no-DB design. Mitigate by running under `systemd` with auto-restart and stable deploys.
- **Abuse / open endpoint** — anyone with the URL can submit credentials and start a job. Mitigations: per-IP rate limit (slowapi), basic CAPTCHA on `/login`, or invite-only access via a shared secret.
- **Pampa account lockout** — wrong credentials repeatedly hammered could lock the Pampa account. Surface clear errors and don't retry on auth failure.
- **Cold start** — Playwright launch ~1–2s on first request after deploy; negligible.

---

## Next steps

1. Provision Oracle Cloud Always Free VM; set up SSH, Docker, firewall, Caddy.
2. Refactor `bot.py` into the three async functions above; verify locally with the existing flow still working.
3. Build FastAPI app with the four endpoints, in-memory `JOB_REGISTRY`, and the janitor task.
4. Build React + Vite frontend (login form → class picker → status view).
5. Containerize backend with Playwright's official Python image.
6. Deploy backend to Oracle VM; deploy frontend to Cloudflare Pages; wire CORS.
7. End-to-end test with a real booking.
8. Harden: rate limiting, CAPTCHA or invite gate, structured logs (no credentials), basic uptime monitoring.
