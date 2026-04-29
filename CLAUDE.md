# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Install dependencies + Playwright Chromium browser: `bash setup.sh`
- Run the bot: `python bot.py`

There is no test suite, linter, or build step.

## Architecture

Single-process Playwright scraper that books a slot on pampafutbol.com. Two modules:

- `bot.py` — async entry point. Three sequential phases: (1) login at `/login` and wait for redirect to `/`; (2) scrape `/alumno/clases-disponibles` once and prompt the user to pick a class by index; (3) poll loop that reloads the page every `INTERVALO_SEGUNDOS` (30s) and clicks the booking chip the moment the chosen class becomes available, then calls `enviar_notificacion` and exits.
- `notificacion.py` — sends an SMTP confirmation email (Gmail by default, overridable via `SMTP_HOST` / `SMTP_PORT`).

The chosen class is matched across reloads by the tuple `(fecha, nivel, sede)` — not by index — because the listing order can change between reloads.

## Scraping selectors (fragile)

The site mixes MUI and styled-components, which forces some non-obvious choices in `obtener_clases`:

- Class cards: `.MuiGrid-item.MuiGrid-grid-xs-12`.
- Level: `text.sc-fLlhyt` — a styled-components hashed class. There is no MUI equivalent for this label, so the hash is the only stable hook. **It will change if the site rebuilds styled-components**, and updating it is the most likely maintenance task.
- Date / availability text: filtered by literal content (`"🗓️"`, `"lugar"`) rather than by class — intentional, because these are the only stable anchors.
- Booking button: `.MuiChip-root`. Availability is read from its `aria-disabled` attribute (NOT from text content or visual state).

When a selector breaks, prefer content-based filters (`.filter(has_text=...)`) over class names — that's the pattern already established for the same reason.

## Configuration

`.env` is loaded by `python-dotenv` at startup. `bot.py` reads `DOCUMENTO` and `PASSWORD` as required (`os.environ[...]` — will KeyError if missing); `notificacion.py` requires `MAIL_FROM`, `MAIL_PASSWORD`, `MAIL_TO`. Gmail requires an App Password, not the account password (see README). The `.env` file is gitignored.

## Rules

Write all the code in english