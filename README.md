# HackPilot

One board for every hackathon deadline. Paste the text of an event page and HackPilot extracts the deadlines, builds a submission checklist, and counts down live on a dashboard sorted by urgency.

> Built using voice dictation with Wispr: the requirements, the spec and the follow-up changes were dictated, not typed.

## Problem

Students who join several hackathons at once lose track of deadlines, submission requirements and team tasks. The details are scattered across Devpost pages, emails and WhatsApp groups, so deadlines get missed and checklist items are forgotten. Most people handle this with scattered notes and calendar reminders.

## Features

- **Paste and extract.** A rule-based parser (regex and keyword matching) finds the event name, link, dates, deadlines, tracks and prizes in pasted text. Every extracted field is editable before saving.
- **Submission checklist.** Auto-generated from the text (GitHub repo, README, demo video, deck, zip file, submission form). Add custom tasks, check them off, reorder them, delete them.
- **Dashboard.** Each event is a card with a live countdown to its key deadline, a checklist progress bar and an urgency colour: green (more than 7 days), amber (under 7 days), red (under 48 hours), grey-brown (passed). Sorted by nearest deadline, overdue events last.
- **Calendar export.** Download one event or every deadline as an `.ics` file, each with a 24-hour reminder.
- **Optional LLM extraction.** Off by default. Set `LLM_API_KEY` and tick the box in the form. Any failure falls back to the rule parser.

## Added in this version

- **Bigger countdown.** A hero panel for the next deadline plus boxed days, hours, minutes and seconds on every card.
- **Dark mode.** Toggle in the header. White is the default and the choice is remembered.
- **Search and filters.** Search by name or type (tracks, tasks, deadline kind) and filter by deadline type and urgency, including "Overdue only".
- **Bot webhooks.** `POST /api/webhook/tasks` and `POST /api/webhook/deadlines` create or update items by `external_id`. Send the header `X-Webhook-Secret` (env `WEBHOOK_SECRET`, default `dev-secret`). The board refreshes every 10 seconds.
- **Safe DB upgrade.** On start, new columns are added to an existing `hackpilot.db`, so old data keeps working.
- **Fixes.** Pasted pages over 20,000 characters were rejected and are now accepted. Unknown `/api/...` routes now return 404, not the HTML page. The review button now reads "Accept details".

Webhook example:

```bash
curl -X POST localhost:8000/api/webhook/tasks -H "X-Webhook-Secret: dev-secret" -H "Content-Type: application/json" \
  -d '{"event_id":1,"external_id":"bot-42","label":"Record demo video","done":true}'
```

## Demo walkthrough (under two minutes)

1. Start the app. The board opens with four sample hackathons: one due in about two days (red), one in nine days, one far away, and one already overdue.
2. Open a card with **Show checklist and dates**, tick a task and watch the progress bar move.
3. Click **Add hackathon**, paste the text of an event page and click **Extract details**.
4. Review the extracted deadlines, tracks, prizes and checklist. Fix anything, then **Accept details**.
5. The new card appears in its place on the board. Use **Add dates to calendar** to export the deadlines.

Screenshots are not bundled. Run the app and save captures of the board into `docs/` if you need them.

## Tech stack

FastAPI, SQLAlchemy and SQLite on the backend. React 18 and Vite on the frontend. SQLite needs no database setup, and FastAPI gives a typed, validated API with little code.

## Setup and run

Requires Python 3.10+ and Node 18+.

```bash
npm run setup     # installs frontend and backend dependencies
npm start         # builds the UI and serves everything on http://localhost:8000
npm test          # runs the backend tests
```

If your system uses `python3` instead of `python`, edit the `start` and `test` scripts in `package.json`.

Development mode with hot reload: run `cd backend && python -m uvicorn app.main:app --reload` in one terminal and `cd frontend && npm run dev` in another, then open http://localhost:5173.

## Environment variables

See `.env.example`. All are optional: `DATABASE_URL`, `SEED_DATA`, `DEFAULT_TZ_OFFSET_MIN`, `LLM_API_KEY`, `LLM_MODEL`.

## Architecture

```
React UI  --/api-->  FastAPI routes  -->  service.py (urgency, sorting, .ics)
                          |                    |
                     parser.py / llm.py     crud.py  -->  SQLite
```

- `parser.py` turns text into a draft event. Nothing is saved until the user reviews it.
- `service.py` decides the key deadline (nearest upcoming submission deadline, else nearest upcoming, else most recent past), the urgency level and the sort order.
- The UI ticks every second to update countdowns and urgency locally, and refreshes from the API after changes.

## Project structure

```
backend/app/    main.py (routes), models.py, schemas.py, parser.py, llm.py, service.py, crud.py, seed.py
backend/tests/  parser, urgency, checklist and API tests
frontend/src/   App.jsx (board, cards, checklist), EventForm.jsx (paste and review), api.js, time.js, styles.css
```

## Known limitations

- The rule parser works best on text with explicit dates (`Oct 18, 2026`, `18 October 2026`, `2026-10-18`). Relative dates such as "next Friday" are not understood.
- Dates with no time are treated as 23:59 in `DEFAULT_TZ_OFFSET_MIN`. Always check the timezone in the review step.
- Single user, no login. Data lives in a local SQLite file.
- Checklist reordering uses up and down buttons, not drag and drop.
- The UI was build-checked and render-checked on the server, but not opened in a real browser during development.
