# Pulse

Music-forward social web app for discovering events, matching with listeners who share your taste, and keeping preferences in sync. Built as a Flask server with a Supabase-backed auth and data layer and a desktop-first UI.

## Features

- **Accounts** - Sign up and log in with Supabase `users` rows and hashed passwords.
- **Onboarding** - Taste quiz that merges into a unified `user_statistics.taste_profile` row.
- **Matchmaking** - Suggested people ranked by taste similarity (`user_statistics`).
- **Events** - Curated event cards, detail modal, and optional Ticketmaster-backed nearby concerts when configured.
- **Pulse assistant** - Client-side helper that links to app routes and curated events.
- **Settings** - Notification and privacy toggles persisted to `user_settings` when signed in (with localStorage fallback).
- **Weekly insights, messaging, profile** - Additional screens wired through the same Flask app.

## Tech stack

| Layer | Choice |
|--------|--------|
| Backend | [Flask](https://flask.palletsprojects.com/) (Python) |
| Database / Auth API | [Supabase](https://supabase.com/) (PostgreSQL via REST) |
| Frontend | Jinja templates, vanilla JS, CSS |

## Prerequisites

- Python **3.10+** recommended  
- A **Supabase** project with URL and API key (anon or service role for server writes)  
- Optional: **Ticketmaster API** key for live concert map data  

## Quick start

### 1. Clone and install

```bash
git clone <repository-url>
cd pulse-app
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the project root (never commit real secrets):

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Project URL from Supabase. |
| `SUPABASE_KEY` or `SUPABASE_SERVICE_ROLE_KEY` | Yes | API key. Prefer **service role** for server-side inserts/updates if RLS blocks anon writes. |
| `FLASK_SECRET` | Recommended | Secret key for Flask sessions (defaults to a dev value if unset). |
| `TICKETMASTER_KEY` | No | Enables live nearby concerts on the concert map. |

Example shape:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
FLASK_SECRET=your-long-random-string
```

### 3. Run the app

```bash
python app.py
```

Then open **http://127.0.0.1:5000** . The dev server runs with `debug=True` when started this way.

For production, use a proper WSGI server (e.g. Gunicorn) and set `debug=False`.

## Project layout (overview)

```
pulse-app/
├── app.py                 # Flask app factory, routes, Supabase access
├── requirements.txt
├── static/
│   ├── css/styles.css
│   └── js/                # Page scripts (settings, chatbot, similarity, etc.)
└── templates/             # Jinja HTML
```

## Development notes

- Session-based routes expect a logged-in user where noted; some routes leave auth relaxed for local development.  
- Curated **events** used by the assistant and events UI live in `app.py` as structured data and stay aligned with `/events` and `/api/events/<id>`.  

## License

Pulse is licensed under the **GNU General Public License v3.0** (GPL-3.0). See the [`LICENSE`](LICENSE) file in this repository for the full license text.

Summary (not a substitute for the license): you may use, modify, and distribute this software under GPL-3.0 terms. Derivatives and combined works must generally also be licensed under the GPL when distributed. See the license for exact conditions and obligations.
