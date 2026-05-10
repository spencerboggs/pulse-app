from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import re
import requests
import json
from werkzeug.utils import secure_filename
from datetime import datetime, timezone

load_dotenv()

# Supabase credentials are read from the environment so local runs need SUPABASE_URL and a suitable API key.
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Prefer service role for server-side writes when RLS is enabled; fall back to anon key.
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ONE unified statistics row per user (onboarding + Spotify sources merged into taste_profile).
USER_STATISTICS_TABLE = "user_statistics"
# Separate table for UI preferences only.
USER_SETTINGS_TABLE = "user_settings"


def _event_nav_entries(events_catalog):
    entries = []
    for event_id, info in events_catalog.items():
        terms = set()
        terms.add(event_id.replace("-", " "))
        for field in ("title", "artist", "location", "genre"):
            val = info.get(field)
            if not val:
                continue
            cleaned = val.lower().replace(",", "").replace(".", "")
            for word in cleaned.split():
                if len(word) > 2:
                    terms.add(word)
        entries.append(
            {
                "id": event_id,
                "title": info["title"],
                "match_terms": sorted(terms),
            }
        )
    return entries


# Curated events power the events grid, map fallback pins, and Pulse assistant links.
EVENTS = {
    "daniel-caesar": {
        "title": "Daniel Caesar Concert",
        "genre": "R&B",
        "artist": "Daniel Caesar",
        "date": "11/23/2025",
        "location": "SoFi Stadium",
        "description": "Experience Daniel Caesar live with new material and fan favorites at SoFi Stadium.",
        "image": "images/placeholder_flawed.jpg",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/danielcaesar/",
            "spotify": "https://open.spotify.com/artist/20wkVLutqVOYrc0kxFs7rA",
        },
    },
    "flawed-mangoes": {
        "title": "Flawed Mangoes Debut Show",
        "genre": "Indie",
        "artist": "Flawed Mangoes",
        "date": "9/28/2025",
        "location": "EchoPlex",
        "description": "Debut headline performance from Flawed Mangoes with support slots from rising locals.",
        "image": "images/placeholder_flawed.jpg",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/",
            "spotify": "https://open.spotify.com/",
        },
    },
    "benson-boone": {
        "title": "Benson Boone Live",
        "genre": "Pop",
        "artist": "Benson Boone",
        "date": "3/14/2026",
        "location": "Kia Forum",
        "description": "An evening of anthemic pop with Benson Boone plus surprise guests.",
        "image": "images/placeholder_flawed.jpg",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/",
            "spotify": "https://open.spotify.com/",
        },
    },
    "neon-nights-festival": {
        "title": "Neon Nights Festival",
        "genre": "Electronic",
        "artist": "Various Artists",
        "date": "7/04/2026",
        "location": "Los Angeles State Historic Park",
        "description": "A daytime festival across two stages celebrating electronic and dance music.",
        "image": "images/placeholder_flawed.jpg",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/",
            "spotify": "https://open.spotify.com/",
        },
    },
}

PULSE_EVENT_NAV = _event_nav_entries(EVENTS)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET", "SUPER_SECRET_KEY")

    # Shared helpers for profiles, Supabase rows, and similarity scoring.

    def slugify(name: str) -> str:
        return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

    def pick_user_image_by_slug(slug: str) -> str:
        uploads_path = os.path.join(app.static_folder, "uploads")
        os.makedirs(uploads_path, exist_ok=True)

        exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")

        # Try exact slug match
        for ext in exts:
            candidate = os.path.join(uploads_path, f"{slug}{ext}")
            if os.path.exists(candidate):
                return url_for("static", filename=f"uploads/{slug}{ext}")

        # fallback to latest upload
        images = [f for f in os.listdir(uploads_path) if f.lower().endswith(exts)]
        if images:
            latest = max(images, key=lambda f: os.path.getmtime(os.path.join(uploads_path, f)))
            return url_for("static", filename="images/profile_placeholder.png")
    
    def get_full_name(u: dict) -> str:
        first = u.get("first_name", "")
        last = u.get("last_name", "")
        full = f"{first} {last}".strip()
        return full if full else u.get("username", "Unknown")

    def get_initials(name: str) -> str:
        parts = name.strip().split()
        return "".join(p[0].upper() for p in parts[:2]) if parts else "?"

    def get_current_user_id() -> str:
        return str(session.get("user_id", ""))

    def get_friend_requests_for_user(user_id: int) -> list:
        try:
            rows = supabase.table("friendships") \
                .select("user_id") \
                .eq("friend_id", str(user_id)) \
                .eq("status", "pending") \
                .execute()
            return rows.data or []
        except Exception:
            return []

    def get_friends_for_user(user_id: int) -> list:
        try:
            f1 = supabase.table("friendships").select("friend_id") \
                .eq("user_id", str(user_id)).eq("status", "accepted").execute()
            f2 = supabase.table("friendships").select("user_id") \
                .eq("friend_id", str(user_id)).eq("status", "accepted").execute()
            ids = list({r["friend_id"] for r in (f1.data or [])} |
                    {r["user_id"] for r in (f2.data or [])})
            return ids
        except Exception:
            return []

    def get_ai_artist_recommendations(seed_artist: str, seed_genre: str) -> list:
        # Placeholder. Replace with real AI or Spotify logic later.
        return [
            {"name": f"Artist similar to {seed_artist}", "genre": seed_genre}
        ]

    # Music profiles mirror the client similarity shape so onboarding and Spotify data stay comparable across APIs.

    def default_music_profile() -> dict:
        return {
            "topArtists": [],
            "topGenres": [],
            "topTracks": [],
            "listeningHistory": [],
            "favoriteDecades": [],
            "audioFeatures": {
                "energy": 0.5,
                "danceability": 0.5,
                "valence": 0.5,
                "acousticness": 0.5,
            },
        }

    GENRE_SLUG_LABEL = {
        "hip_hop": "hip hop",
        "pop": "pop",
        "rock": "rock",
        "r_b": "r&b",
        "electronic": "electronic",
        "indie": "indie",
        "jazz": "jazz",
        "other": "other",
    }

    def build_music_profile_from_quiz(raw: dict) -> dict:
        base = default_music_profile()
        slug = (raw.get("favorite_genre") or "").strip()
        if slug in GENRE_SLUG_LABEL:
            base["topGenres"] = [GENRE_SLUG_LABEL[slug]]

        listen = raw.get("listening_frequency") or ""
        listen_energy = {
            "daily": 0.88,
            "regular": 0.74,
            "weekly": 0.58,
            "occasional": 0.42,
        }.get(listen, 0.55)

        concerts = raw.get("concert_frequency") or ""
        dance = {
            "monthly": 0.85,
            "occasional": 0.62,
            "rarely": 0.45,
            "never": 0.35,
        }.get(concerts, 0.5)

        discover = raw.get("music_discovery") or ""
        acousticness = 0.35 if discover == "radio" else 0.55 if discover == "streaming" else 0.45

        base["audioFeatures"] = {
            "energy": listen_energy,
            "danceability": dance,
            "valence": min(1.0, (listen_energy + dance) / 2 + 0.05),
            "acousticness": acousticness,
        }
        base["quiz_meta"] = {
            "listening_frequency": listen,
            "concert_frequency": concerts,
            "music_discovery": discover,
            "matchmaking_priority": raw.get("matchmaking_priority"),
            "spotify_integration": raw.get("spotify_integration"),
        }
        return base

    # Jaccard index on two string lists powers artist, genre, track, and decade terms.
    def _jaccard_list(a: list, b: list) -> float:
        if not a or not b:
            return 0.0
        s1 = {str(x).lower() for x in a}
        s2 = {str(x).lower() for x in b}
        inter = len(s1 & s2)
        union = len(s1 | s2)
        return inter / union if union else 0.0

    # Cosine similarity on the four audio feature scalars stored inside taste profiles.
    def _audio_cosine(f1: dict, f2: dict) -> float:
        keys = ["energy", "danceability", "valence", "acousticness"]
        dot = 0.0
        m1 = 0.0
        m2 = 0.0
        for k in keys:
            v1 = float((f1 or {}).get(k) or 0)
            v2 = float((f2 or {}).get(k) or 0)
            dot += v1 * v2
            m1 += v1 * v1
            m2 += v2 * v2
        mag = (m1 ** 0.5) * (m2 ** 0.5)
        return dot / mag if mag > 0 else 0.0

    # Weighted blend of list overlap and feature cosine, matches the client SimilarityEngine weights.
    def similarity_between_profiles(p1: dict, p2: dict) -> float:
        if not p1 or not p2:
            return 0.0
        w = {"artists": 0.3, "genres": 0.25, "tracks": 0.2, "audioFeatures": 0.15, "decades": 0.1}
        artist_score = _jaccard_list(p1.get("topArtists") or [], p2.get("topArtists") or [])
        genre_score = _jaccard_list(p1.get("topGenres") or [], p2.get("topGenres") or [])
        track_score = _jaccard_list(p1.get("topTracks") or [], p2.get("topTracks") or [])
        audio_score = _audio_cosine(p1.get("audioFeatures") or {}, p2.get("audioFeatures") or {})
        decade_score = _jaccard_list(p1.get("favoriteDecades") or [], p2.get("favoriteDecades") or [])
        total = (
            artist_score * w["artists"]
            + genre_score * w["genres"]
            + track_score * w["tracks"]
            + audio_score * w["audioFeatures"]
            + decade_score * w["decades"]
        )
        return round(total * 100) / 100

    def fetch_user_statistics(user_id: str):
        try:
            res = supabase.table(USER_STATISTICS_TABLE).select("*").eq("user_id", user_id).limit(1).execute()
            rows = res.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def fetch_user_settings_row(user_id: str):
        try:
            res = supabase.table(USER_SETTINGS_TABLE).select("*").eq("user_id", user_id).limit(1).execute()
            rows = res.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def statistics_or_settings_table_error_msg(exc: Exception) -> str:
        err = str(exc)
        if "user_statistics" in err or USER_SETTINGS_TABLE in err or "PGRST205" in err or "does not exist" in err:
            return (
                "Required tables are missing. Run supabase/migrations/002_user_statistics_and_settings.sql "
                "in the Supabase SQL editor."
            )
        return err

    def taste_profile_from_row(row: dict | None) -> dict:
        if not row:
            return default_music_profile()
        tp = row.get("taste_profile")
        if isinstance(tp, dict) and tp:
            return tp
        # Legacy column name if migrating manually
        legacy = row.get("music_profile")
        if isinstance(legacy, dict) and legacy:
            return legacy
        return default_music_profile()

    def merge_quiz_into_taste(existing_taste: dict | None, quiz_derived: dict) -> dict:
        """Merge onboarding-derived taste into existing (preserves Spotify-rich fields when stronger)."""
        base = existing_taste if isinstance(existing_taste, dict) else default_music_profile()
        q = quiz_derived if isinstance(quiz_derived, dict) else default_music_profile()
        out = default_music_profile()
        out["topGenres"] = list(
            dict.fromkeys([*(base.get("topGenres") or []), *(q.get("topGenres") or [])])
        )
        out["topArtists"] = list(dict.fromkeys([*(base.get("topArtists") or []), *(q.get("topArtists") or [])]))[:40]
        out["topTracks"] = list(dict.fromkeys([*(base.get("topTracks") or []), *(q.get("topTracks") or [])]))[:40]
        out["favoriteDecades"] = list(
            dict.fromkeys([*(base.get("favoriteDecades") or []), *(q.get("favoriteDecades") or [])])
        )
        out["listeningHistory"] = base.get("listeningHistory") or q.get("listeningHistory") or []

        ab = base.get("audioFeatures") or {}
        aq = q.get("audioFeatures") or {}
        if ab and aq:
            keys = ["energy", "danceability", "valence", "acousticness"]
            out["audioFeatures"] = {
                k: round((float(ab.get(k) or 0) + float(aq.get(k) or 0)) / 2, 4) for k in keys
            }
        else:
            out["audioFeatures"] = aq or ab or default_music_profile()["audioFeatures"]

        qmeta = q.get("quiz_meta") or {}
        if qmeta:
            merged_meta = {**(base.get("quiz_meta") or {}), **qmeta}
            out["quiz_meta"] = merged_meta
        return out

    def merge_spotify_into_taste(existing_taste: dict | None, spotify_taste: dict) -> dict:
        """Prefer Spotify lists when present; blend audioFeatures."""
        base = existing_taste if isinstance(existing_taste, dict) else default_music_profile()
        s = spotify_taste if isinstance(spotify_taste, dict) else default_music_profile()
        out = default_music_profile()
        out["topArtists"] = (s.get("topArtists") or base.get("topArtists") or [])[:40]
        out["topGenres"] = list(
            dict.fromkeys([*(s.get("topGenres") or []), *(base.get("topGenres") or [])])
        )
        out["topTracks"] = (s.get("topTracks") or base.get("topTracks") or [])[:40]
        out["favoriteDecades"] = base.get("favoriteDecades") or s.get("favoriteDecades") or []
        out["listeningHistory"] = s.get("listeningHistory") or base.get("listeningHistory") or []
        ab = base.get("audioFeatures") or {}
        asp = s.get("audioFeatures") or {}
        if asp:
            keys = ["energy", "danceability", "valence", "acousticness"]
            out["audioFeatures"] = {
                k: round(float(asp.get(k) or ab.get(k) or 0), 4) if asp.get(k) is not None else float(ab.get(k) or 0)
                for k in keys
            }
        else:
            out["audioFeatures"] = ab or default_music_profile()["audioFeatures"]
        if base.get("quiz_meta"):
            out["quiz_meta"] = base.get("quiz_meta")
        return out

    def taste_from_spotify_payload(blob: dict) -> dict:
        """Normalize client-provided Spotify aggregates into the shared taste shape."""
        base = default_music_profile()
        items = blob.get("top_artists") or blob.get("topArtists") or []
        if isinstance(items, list):
            base["topArtists"] = []
            for it in items[:40]:
                if isinstance(it, str):
                    base["topArtists"].append(it)
                elif isinstance(it, dict) and it.get("name"):
                    base["topArtists"].append(it["name"])
        genres = blob.get("top_genres") or blob.get("topGenres") or []
        if isinstance(genres, list):
            base["topGenres"] = [str(g).lower() for g in genres[:30]]
        tracks = blob.get("top_tracks") or blob.get("topTracks") or []
        if isinstance(tracks, list):
            base["topTracks"] = []
            for it in tracks[:40]:
                if isinstance(it, str):
                    base["topTracks"].append(it)
                elif isinstance(it, dict) and it.get("name"):
                    base["topTracks"].append(it["name"])
        af = blob.get("audioFeatures") or blob.get("audio_features") or {}
        if isinstance(af, dict) and af:
            base["audioFeatures"] = {
                "energy": float(af.get("energy", 0.5)),
                "danceability": float(af.get("danceability", 0.5)),
                "valence": float(af.get("valence", 0.5)),
                "acousticness": float(af.get("acousticness", 0.5)),
            }
        return base


    # Route handlers for pages and JSON endpoints used by the Pulse web client.

    @app.route("/")
    def index():
        return redirect(url_for("home"))

    # Auth renders login and signup forms that POST to routes backed by the Supabase users table.
    @app.route("/auth")
    def auth():
        return render_template("auth.html")

    # Sign up inserts a new row into the Supabase users table, hashes the password, and stores the user id in the session.
    @app.route("/signup", methods=["POST"])
    def signup():
        first_name = request.form["firstName"]
        last_name = request.form["lastName"]
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]
        confirm = request.form["confirmPassword"]

        # Reject early when the two password fields differ so the database never sees a partial row.
        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth"))

        # Username and email must be unique so login can resolve a single record later.
        existing = supabase.table("users") \
            .select("id") \
            .or_(f"username.eq.{username},email.eq.{email}") \
            .execute()

        if existing.data:
            flash("Username or email already exists.", "error")
            return redirect(url_for("auth"))

        # Werkzeug hashing keeps plain passwords out of Supabase and out of logs.
        password_hash = generate_password_hash(password)

        result = supabase.table("users").insert({
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "email": email,
            "password_hash": password_hash
        }).execute()

        user = result.data[0]

        # Session keys drive greeting copy on home and gate routes that require authentication.
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("home"))

    # Log in validates credentials against Supabase and restores the session with user id and username.
    @app.route("/login", methods=["POST"])
    def login():
        identity = request.form["identity"]
        password = request.form["password"]

        # Happy path loads one user by username or email then verifies the stored hash.
        if supabase:
            try:
                query = supabase.table("users") \
                    .select("*") \
                    .or_(f"username.eq.{identity},email.eq.{identity}") \
                    .limit(1) \
                    .execute()
                user = query.data[0] if query.data else None
                if not user or not check_password_hash(user.get("password_hash", ""), password):
                    flash("Invalid credentials.", "error")
                    return redirect(url_for("auth"))
                session.clear()
                session["user_id"] = str(user["id"])
                session["username"] = user["username"]
                return redirect(url_for("home"))
            except Exception as e:
                flash(f"Login error: {e}", "error")
                return redirect(url_for("auth"))

        # Offline fallback keeps local demos usable when Supabase is unreachable.
        session.clear()
        session["user_id"] = "test_user_123"
        session["username"] = identity if identity else "test_user"
        return redirect(url_for("home"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth"))

    # Home is the signed in hub that routes navigation into matchmaking, events, settings, and tools.
    @app.route("/home")
    def home():
        # Auth check disabled for development. Re enable when every visitor must be signed in.
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))

        username = session.get("username", "Guest")
        return render_template("home.html", username=username)

    @app.route("/profile")
    def profile():
        # Auth check disabled for development. Re enable when profile must be private.
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))

        username = session.get("username", "Guest")
        slug = slugify(username)
        img_url = pick_user_image_by_slug(slug)
        favorite_insight_ids = session.get("favorite_insights", [])
        followed_insights = [item for item in WEEKLY_INSIGHTS if item["id"] in favorite_insight_ids]
        favorite_event_ids = session.get("favorite_events", [])
        followed_events = [
            {"id": eid, **EVENTS[eid]}
            for eid in favorite_event_ids
            if eid in EVENTS
        ]
        return render_template(
            "profile.html",
            img_url=img_url,
            display_name=username,
            followed_insights=followed_insights,
            followed_events=followed_events,
        )
    ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}

    def allowed_image(filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTS

#Used to Change PFP
    @app.route("/profile/upload-picture", methods=["POST"])
    def upload_profile_picture():
        if "user_id" not in session:
            return redirect(url_for("auth"))

        if "profile_picture" not in request.files:
            flash("No file selected.", "error")
            return redirect(url_for("profile"))

        file = request.files["profile_picture"]

        if not file or file.filename == "":
            flash("No file selected.", "error")
            return redirect(url_for("profile"))

        if not allowed_image(file.filename):
            flash("Please upload a PNG, JPG, JPEG, WEBP, or GIF image.", "error")
            return redirect(url_for("profile"))

        slug = slugify(session["username"])
        ext = file.filename.rsplit(".", 1)[1].lower()

        uploads_path = os.path.join(app.static_folder, "uploads")
        os.makedirs(uploads_path, exist_ok=True)

    
        for old_ext in ALLOWED_IMAGE_EXTS:
            old_path = os.path.join(uploads_path, f"{slug}.{old_ext}")
            if os.path.exists(old_path):
                os.remove(old_path)

        filename = secure_filename(f"{slug}.{ext}")
        save_path = os.path.join(uploads_path, filename)
        file.save(save_path)

        flash("Profile picture updated!", "success")
        return redirect(url_for("profile"))


    @app.route("/u/<path:username>")
    def user_profile(username):
        slug = slugify(username)
        img_url = pick_user_image_by_slug(slug)
        return render_template("profile_view.html", img_url=img_url, display_name=username)

    @app.get("/search_users")
    def search_users():
        if "user_id" not in session:
            return jsonify({"users": []})

        try:
            current_user_id = int(session.get("user_id"))
        except (TypeError, ValueError):
            return jsonify({"users": []})

        q = (request.args.get("q") or "").strip()

        if not q:
            return jsonify({"users": []})

        result = supabase.table("users") \
            .select("id, username, email, first_name, last_name") \
            .or_(f"username.ilike.%{q}%,email.ilike.%{q}%,first_name.ilike.%{q}%,last_name.ilike.%{q}%") \
            .limit(20) \
            .execute()

        users = []
        for u in (result.data or []):
            try:
                user_id = int(u.get("id"))
            except (TypeError, ValueError):
                continue

            if user_id == current_user_id:
                continue

            display_name = get_full_name(u)

            users.append({
                "id": user_id,
                "username": u.get("username"),
                "name": display_name,
                "handle": f"@{u.get('username')}" if u.get("username") else "",
                "initials": get_initials(display_name)
            })

        return jsonify({"users": users})

    @app.route("/api/artist-recommendations")
    def artist_recommendations():
        if "user_id" not in session:
            return jsonify({"recommendations": []}), 401

        favorite_artist = request.args.get("artist", "Tyler, The Creator")
        favorite_genre = request.args.get("genre", "Neo-Soul")

        recommendations = get_ai_artist_recommendations(
            seed_artist=favorite_artist,
            seed_genre=favorite_genre
        )

        return jsonify({"recommendations": recommendations})

    @app.route("/test_supabase")
    def test_supabase():
        data = supabase.table("profiles").select("*").execute()
        return {"data": data.data}

    # Secondary pages include listings, maps, insights, and messaging shells used across the product surface.

    @app.route("/events")
    def events():
        return render_template("events.html", events=EVENTS)

    @app.route("/api/events/<event_id>")
    def api_event_details(event_id):
        event = EVENTS.get(event_id)
        if not event:
            return jsonify({"error": "Event not found"}), 404
        event_out = dict(event)
        event_out["image_url"] = url_for("static", filename=event["image"])
        return jsonify(event_out)


    @app.route("/concert-map")
    def concert_map():
        return render_template("concert_map.html")

    @app.get("/api/nearby-concerts")
    def api_nearby_concerts():
        lat = request.args.get("lat", type=float)
        lng = request.args.get("lng", type=float)
        radius = request.args.get("radius", 25, type=int)

        tm_key = os.getenv("TICKETMASTER_KEY")
        if tm_key and lat is not None and lng is not None:
            try:
                r = requests.get(
                    "https://app.ticketmaster.com/discovery/v2/events.json",
                    params={
                        "apikey": tm_key,
                        "latlong": f"{lat},{lng}",
                        "radius": radius,
                        "unit": "miles",
                        "classificationName": "music",
                        "size": 30,
                        "sort": "date,asc",
                    },
                    timeout=8,
                )
                if r.ok:
                    raw = r.json()
                    events_out = []
                    for e in raw.get("_embedded", {}).get("events", []):
                        venues = e.get("_embedded", {}).get("venues", [{}])
                        venue = venues[0] if venues else {}
                        loc = venue.get("location", {})
                        try:
                            elat = float(loc.get("latitude", 0))
                            elng = float(loc.get("longitude", 0))
                        except (TypeError, ValueError):
                            continue
                        if not elat and not elng:
                            continue
                        images = e.get("images", [])
                        img = next((i["url"] for i in images if i.get("ratio") == "16_9" and i.get("width", 0) >= 640), None)
                        events_out.append({
                            "name": e.get("name", "Concert"),
                            "date": e.get("dates", {}).get("start", {}).get("localDate", "TBA"),
                            "time": e.get("dates", {}).get("start", {}).get("localTime", ""),
                            "venue": venue.get("name", ""),
                            "city": venue.get("city", {}).get("name", ""),
                            "lat": elat,
                            "lng": elng,
                            "url": e.get("url", "#"),
                            "image": img,
                        })
                    return jsonify({"events": events_out, "source": "ticketmaster"})
            except Exception:
                pass

        # Fallback: use app's static events (geocode approximated)
        static_fallback = [
            {"name": e["title"], "date": e["date"], "time": "", "venue": e["location"],
             "city": "Los Angeles", "lat": 34.0195 + i * 0.03, "lng": -118.4912 + i * 0.02,
             "url": e.get("ticket_url", "#"), "image": None}
            for i, e in enumerate(EVENTS.values())
        ]
        return jsonify({"events": static_fallback, "source": "static"})

    # Settings reads and writes preferences through user_settings while mirroring toggles in the browser for responsiveness.
    @app.route("/settings")
    def settings():
        # Auth check disabled for development. Re enable when settings must be private.
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))
        return render_template("settings.html")

    # Pulse assistant receives curated event metadata so suggested links align with listings on the events page.
    @app.route("/chatbot")
    def chatbot():
        if "user_id" not in session:
            return redirect(url_for("auth"))
        return render_template("chatbot.html", pulse_event_nav=PULSE_EVENT_NAV)

    # Onboarding captures taste signals that merge into user_statistics alongside future Spotify imports.
    @app.route("/onboarding-quiz")
    def onboarding_quiz():
        if "user_id" not in session:
            return redirect(url_for("auth"))
        return render_template("onboarding_quiz.html")

    # Quiz submission persists answers under onboarding and refreshes the computed taste_profile row for matching.
    @app.route("/api/onboarding/submit", methods=["POST"])
    def api_onboarding_submit():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        try:
            uid = int(session["user_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid session user"}), 400

        # Field names align with the onboarding template so FormData style bodies deserialize cleanly.
        raw = request.get_json(silent=True) or {}
        quiz_taste = build_music_profile_from_quiz(raw)
        now = datetime.now(timezone.utc).isoformat()

        try:
            supabase.table("users").update({"quiz_complete": True}).eq("id", uid).execute()
        except Exception as e:
            return jsonify({"error": f"users update failed: {e}"}), 500

        prev = fetch_user_statistics(str(uid))
        existing_taste = taste_profile_from_row(prev)
        # merge_quiz_into_taste preserves Spotify derived slices when quiz answers refresh.
        merged_taste = merge_quiz_into_taste(existing_taste, quiz_taste)

        try:
            prev_onb = (prev or {}).get("onboarding") if isinstance(prev, dict) else {}
            if not isinstance(prev_onb, dict):
                prev_onb = {}
            # Upsert keeps onboarding JSON, merged taste_profile, and prior spotify blob in one row.
            supabase.table(USER_STATISTICS_TABLE).upsert(
                {
                    "user_id": uid,
                    "onboarding": raw,
                    "taste_profile": merged_taste,
                    "spotify": (prev or {}).get("spotify") if isinstance(prev, dict) else {},
                    "updated_at": now,
                },
                on_conflict="user_id",
            ).execute()
        except Exception as e:
            return jsonify({"error": statistics_or_settings_table_error_msg(e)}), 503

        return jsonify({"ok": True, "music_profile": merged_taste, "taste_profile": merged_taste})

    @app.route("/api/statistics/spotify-sync", methods=["POST"])
    def api_statistics_spotify_sync():
        # Spotify sync merges streaming aggregates into the unified user_statistics taste_profile row.
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        try:
            uid = int(session["user_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid session user"}), 400

        body = request.get_json(silent=True) or {}
        spotify_blob = body.get("spotify") if isinstance(body.get("spotify"), dict) else body
        if not isinstance(spotify_blob, dict):
            spotify_blob = {}
        explicit_taste = body.get("taste_profile") if isinstance(body.get("taste_profile"), dict) else None
        derived = explicit_taste if explicit_taste else taste_from_spotify_payload(spotify_blob)

        now = datetime.now(timezone.utc).isoformat()
        prev = fetch_user_statistics(str(uid))
        existing_taste = taste_profile_from_row(prev)
        merged_taste = merge_spotify_into_taste(existing_taste, derived)

        try:
            supabase.table(USER_STATISTICS_TABLE).upsert(
                {
                    "user_id": uid,
                    "spotify": spotify_blob,
                    "taste_profile": merged_taste,
                    "onboarding": (prev or {}).get("onboarding") if isinstance(prev, dict) else {},
                    "updated_at": now,
                },
                on_conflict="user_id",
            ).execute()
        except Exception as e:
            return jsonify({"error": statistics_or_settings_table_error_msg(e)}), 503

        return jsonify({"ok": True, "taste_profile": merged_taste, "music_profile": merged_taste})

    # Settings load returns the preferences JSON stored in user_settings for the signed in account.
    @app.route("/api/settings/load")
    def api_settings_load():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        try:
            uid = int(session["user_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid session user"}), 400
        try:
            row = fetch_user_settings_row(str(uid))
        except Exception as e:
            return jsonify({"error": str(e), "preferences": {}}), 200
        prefs = (row or {}).get("preferences")
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except Exception:
                prefs = {}
        if not isinstance(prefs, dict):
            prefs = {}
        return jsonify({"preferences": prefs})

    # Settings save merges incoming preference keys into user_settings without dropping untouched keys.
    @app.route("/api/settings/save", methods=["POST"])
    def api_settings_save():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        try:
            uid = int(session["user_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid session user"}), 400
        body = request.get_json(silent=True) or {}
        new_prefs = body.get("preferences")
        if not isinstance(new_prefs, dict):
            return jsonify({"error": "Expected { preferences: { ... } }"}), 400
        now = datetime.now(timezone.utc).isoformat()
        row = fetch_user_settings_row(str(uid))
        existing = (row or {}).get("preferences")
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except Exception:
                existing = {}
        if not isinstance(existing, dict):
            existing = {}
        merged = {**existing, **new_prefs}
        try:
            supabase.table(USER_SETTINGS_TABLE).upsert(
                {
                    "user_id": uid,
                    "preferences": merged,
                    "updated_at": now,
                },
                on_conflict="user_id",
            ).execute()
        except Exception as e:
            return jsonify({"error": statistics_or_settings_table_error_msg(e)}), 503
        return jsonify({"ok": True})

    @app.route("/api/me/music-profile")
    def api_me_music_profile():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        row = fetch_user_statistics(str(session["user_id"]))
        tp = taste_profile_from_row(row)
        return jsonify({"music_profile": tp, "taste_profile": tp})

    @app.route("/api/users/<int:user_id>/music-profile")
    def api_user_music_profile(user_id: int):
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        row = fetch_user_statistics(str(user_id))
        tp = taste_profile_from_row(row)
        return jsonify({"music_profile": tp, "taste_profile": tp})

    @app.route("/api/matchmaking/candidate-profiles")
    def api_matchmaking_candidate_profiles():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        try:
            res = supabase.table("users").select("id, username, first_name, last_name").neq(
                "id", int(session["user_id"])
            ).limit(200).execute()
        except Exception as e:
            return jsonify({"error": str(e), "users": []}), 200
        others = res.data or []
        if not others:
            return jsonify({"users": []})
        ids = [str(u["id"]) for u in others]
        profiles = {}
        try:
            pr = supabase.table(USER_STATISTICS_TABLE).select("user_id, taste_profile").in_("user_id", ids).execute()
            for row in pr.data or []:
                profiles[str(row["user_id"])] = taste_profile_from_row(row)
        except Exception:
            for oid in ids:
                profiles[oid] = default_music_profile()
        out = []
        for u in others:
            oid = str(u["id"])
            display_name = get_full_name(u)
            tp = profiles.get(oid) or default_music_profile()
            out.append(
                {
                    "id": int(u["id"]),
                    "username": u.get("username"),
                    "name": display_name,
                    "music_profile": tp,
                    "taste_profile": tp,
                }
            )
        return jsonify({"users": out})

    # Loads peer profiles, scores with similarity_between_profiles, applies a pending friend filter, returns top rows.
    def _ranked_similar_users(uid: int, limit: int = 10):
        res = supabase.table("users").select("id, username, first_name, last_name").neq("id", uid).limit(200).execute()
        others = res.data or []
        if not others:
            return []
        ids = [str(u["id"]) for u in others]
        profiles = {}
        try:
            pr = supabase.table(USER_STATISTICS_TABLE).select("user_id, taste_profile").in_("user_id", ids).execute()
            for row in pr.data or []:
                profiles[str(row["user_id"])] = taste_profile_from_row(row)
        except Exception:
            pass
        my_row = fetch_user_statistics(str(uid))
        my_p = taste_profile_from_row(my_row)
        pending = set()
        try:
            prq = supabase.table("friendships").select("friend_id").eq("user_id", str(uid)).eq("status", "pending").execute()
            for r in prq.data or []:
                pending.add(str(r.get("friend_id")))
        except Exception:
            pass
        scored = []
        for u in others:
            oid = str(u["id"])
            op = profiles.get(oid) or default_music_profile()
            score = similarity_between_profiles(my_p, op)
            display_name = get_full_name(u)
            scored.append(
                {
                    "id": int(u["id"]),
                    "username": u.get("username"),
                    "name": display_name,
                    "handle": f"@{u['username']}" if u.get("username") else "",
                    "initials": get_initials(display_name),
                    "similarity": score,
                    "requested": oid in pending,
                }
            )
        scored.sort(key=lambda x: (-x["similarity"], x.get("username") or ""))
        return scored[:limit]

    # Similar users ranks other accounts by taste_profile similarity for matchmaking style discovery lists.
    @app.route("/api/suggested-users")
    @app.route("/api/similarity/top-matches")
    def api_suggested_users():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in", "users": []}), 401
        try:
            uid = int(session["user_id"])
        except (TypeError, ValueError):
            return jsonify({"users": []})
        try:
            ranked = _ranked_similar_users(uid, limit=10)
        except Exception as e:
            return jsonify({"users": [], "error": str(e)})
        return jsonify({"users": ranked})

    WEEKLY_INSIGHTS = [
        {
            "id": "tyler-chromakopia-tour",
            "title": "Tyler, The Creator Announces CHROMAKOPIA World Tour Dates",
            "summary": "Tyler confirmed a 40-city world tour supporting his CHROMAKOPIA album. The LA stop at the Kia Forum sold out in under 12 minutes. A second date has been added.",
            "badges": ["Tour", "Hip-Hop"],
            "date": "Jan 18"
        },
        {
            "id": "sza-sos-deluxe",
            "title": "SZA Drops SOS Deluxe With Three Surprise New Singles",
            "summary": "The long-awaited SOS Deluxe arrived featuring 'F2F', 'Needed' and a collab with Pharrell. Streaming records broken within the first hour of release.",
            "badges": ["New Music", "R&B"],
            "date": "Feb 4"
        },
        {
            "id": "kendrick-stadium",
            "title": "Kendrick Lamar Books Dodger Stadium for One-Night Show",
            "summary": "Hot off his Super Bowl halftime performance, Kendrick is returning to LA for a massive hometown show. Proceeds benefit Compton youth arts programs.",
            "badges": ["Concert", "Hip-Hop"],
            "date": "Mar 15"
        },
        {
            "id": "frank-ocean-pharrell",
            "title": "Frank Ocean Spotted In Studio with Pharrell — Album Incoming?",
            "summary": "Multiple sources confirm Frank Ocean has been working with Pharrell Williams for the past three months. No official statement yet, but fans are speculating a 2026 release.",
            "badges": ["Rumour", "R&B"],
            "date": "Apr 10"
        },
        {
            "id": "daniel-caesar-collab",
            "title": "Daniel Caesar Teases Joint Project with Steve Lacy",
            "summary": "Caesar posted a 15-second studio clip on Instagram featuring what sounds like Lacy's signature guitar work. The caption simply read: 'soon.'",
            "badges": ["Collaboration", "Neo-Soul"],
            "date": "Apr 20"
        },
        {
            "id": "bad-bunny-residency",
            "title": "Bad Bunny Announces 10-Night Las Vegas Residency",
            "summary": "The reggaeton superstar is taking the Vegas residency route, booking ten nights at Sphere. Production is reportedly unlike anything seen before.",
            "badges": ["Residency", "Latin"],
            "date": "May 3"
        },
    ]

    def _activity_file():
        path = os.path.join(app.static_folder, "data")
        os.makedirs(path, exist_ok=True)
        return os.path.join(path, "activity.json")

    def _load_activity():
        f = _activity_file()
        if os.path.exists(f):
            try:
                with open(f) as fh:
                    return json.load(fh)
            except Exception:
                pass
        return []

    def _append_activity(entry):
        log = _load_activity()
        log.insert(0, entry)
        with open(_activity_file(), "w") as fh:
            json.dump(log[:200], fh)

    @app.route("/weekly-insights")
    def weekly_insights():
        favorites = session.get("favorite_insights", [])
        insights = []
        for item in WEEKLY_INSIGHTS:
            insight = dict(item)
            insight["is_favorited"] = item["id"] in favorites
            insights.append(insight)
        return render_template("weekly_insights.html", insights=insights)

    @app.post("/api/insights/favorite/<insight_id>")
    def api_toggle_favorite_insight(insight_id):
        favorites = session.get("favorite_insights", [])
        if insight_id in favorites:
            favorites.remove(insight_id)
            favorited = False
        else:
            favorites.append(insight_id)
            favorited = True
            insight = next((i for i in WEEKLY_INSIGHTS if i["id"] == insight_id), None)
            if insight:
                _append_activity({
                    "user_id": str(session.get("user_id", "guest")),
                    "username": session.get("username", "someone"),
                    "type": "liked_insight",
                    "title": insight["title"],
                    "time": "Just now",
                })
        session["favorite_insights"] = favorites
        return jsonify({"favorited": favorited})

    @app.get("/api/events-feed")
    def api_events_feed():
        favorites = session.get("favorite_events", [])
        out = []
        for event_id, e in EVENTS.items():
            out.append({
                "id": event_id,
                "title": e["title"],
                "genre": e["genre"],
                "date": e["date"],
                "location": e["location"],
                "description": e["description"],
                "is_favorited": event_id in favorites,
            })
        return jsonify({"events": out})

    @app.post("/api/events-feed/favorite/<event_id>")
    def api_toggle_favorite_event(event_id):
        if event_id not in EVENTS:
            return jsonify({"error": "Event not found"}), 404
        favorites = session.get("favorite_events", [])
        if event_id in favorites:
            favorites.remove(event_id)
            favorited = False
        else:
            favorites.append(event_id)
            favorited = True
            _append_activity({
                "user_id": str(session.get("user_id", "guest")),
                "username": session.get("username", "someone"),
                "type": "liked_event",
                "title": EVENTS[event_id]["title"],
                "time": "Just now",
            })
        session["favorite_events"] = favorites
        return jsonify({"favorited": favorited})

    @app.get("/api/friends-activity")
    def api_friends_activity():
        current_uid = str(session.get("user_id", ""))
        try:
            uid_int = int(current_uid)
            friend_ids = {str(fid) for fid in get_friends_for_user(uid_int)}
        except (TypeError, ValueError):
            friend_ids = set()
        log = _load_activity()
        activity = [e for e in log if str(e.get("user_id")) in friend_ids]
        return jsonify({"activity": activity[:20]})

    ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    @app.get("/api/event-photos")
    def get_event_photos():
        photos_dir = os.path.join(app.static_folder, "uploads", "event-photos")
        os.makedirs(photos_dir, exist_ok=True)
        meta_path = os.path.join(photos_dir, "metadata.json")
        all_photos = json.loads(open(meta_path).read()) if os.path.exists(meta_path) else []
        current_uid = str(session.get("user_id", ""))
        try:
            uid_int = int(current_uid)
            friend_ids = {str(fid) for fid in get_friends_for_user(uid_int)}
        except (TypeError, ValueError):
            friend_ids = set()
        allowed = friend_ids | {current_uid}
        if current_uid and allowed:
            photos = [p for p in all_photos if str(p.get("user_id", "")) in allowed]
        else:
            photos = all_photos
        return jsonify({"photos": photos})

    @app.post("/api/event-photos")
    def upload_event_photo():
        import time as _time, uuid as _uuid
        caption = (request.form.get("caption") or "").strip()
        file = request.files.get("photo")

        photos_dir = os.path.join(app.static_folder, "uploads", "event-photos")
        os.makedirs(photos_dir, exist_ok=True)
        meta_path = os.path.join(photos_dir, "metadata.json")
        photos = json.loads(open(meta_path).read()) if os.path.exists(meta_path) else []

        photo_url = None
        if file and file.filename:
            _, ext = os.path.splitext(file.filename.lower())
            if ext not in ALLOWED_PHOTO_EXTS:
                return jsonify({"error": "Invalid file type"}), 400
            filename = f"{int(_time.time())}_{_uuid.uuid4().hex[:8]}{ext}"
            file.save(os.path.join(photos_dir, filename))
            photo_url = f"/static/uploads/event-photos/{filename}"

        if not photo_url and not caption:
            return jsonify({"error": "Provide a caption or photo"}), 400

        entry = {
            "url": photo_url,
            "caption": caption or "",
            "username": session.get("username", "Guest"),
            "user_id": str(session.get("user_id", "")),
            "time": "Just now",
        }
        photos.insert(0, entry)
        with open(meta_path, "w") as fh:
            json.dump(photos[:200], fh)

        _append_activity({
            "user_id": str(session.get("user_id", "guest")),
            "username": session.get("username", "someone"),
            "type": "posted_photo",
            "caption": caption or "shared a moment",
            "photo_url": photo_url,
            "time": "Just now",
        })

        return jsonify({"status": "uploaded", "url": photo_url})

    @app.route("/friends/list")
    def friends_list():
        if "user_id" not in session:
            return jsonify({"friends": []})
        try:
            uid = str(session["user_id"])
            f1 = supabase.table("friendships").select("friend_id") \
                .eq("user_id", uid).eq("status", "accepted").execute()
            f2 = supabase.table("friendships").select("user_id") \
                .eq("friend_id", uid).eq("status", "accepted").execute()

            ids = list({r["friend_id"] for r in (f1.data or [])} |
                       {r["user_id"] for r in (f2.data or [])})
            if not ids:
                return jsonify({"friends": []})

            users = supabase.table("users").select("id, username") \
                .in_("id", ids).execute()
            return jsonify({"friends": [
                {"id": u["id"], "username": u["username"]}
                for u in (users.data or [])
            ]})
        except Exception as e:
            return jsonify({"friends": [], "error": str(e)})

    @app.route("/friend/add", methods=["POST"])
    @app.route("/api/add-friend", methods=["POST"])
    def add_friend():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json()
        friend_id = data.get("friend_id")
        if not friend_id or str(friend_id) == str(session["user_id"]):
            return jsonify({"error": "Invalid"}), 400
        try:
            supabase.table("friendships").upsert({
                "user_id": str(session["user_id"]),
                "friend_id": str(friend_id),
                "status": "pending"
            }).execute()
            return jsonify({"status": "pending"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/friend/requests")
    @app.route("/api/friend-requests")
    def friend_requests():
        if "user_id" not in session:
            return jsonify({"requests": []})
        try:
            rows = supabase.table("friendships") \
                .select("user_id") \
                .eq("friend_id", str(session["user_id"])) \
                .eq("status", "pending") \
                .execute()

            sender_ids = [r["user_id"] for r in (rows.data or [])]
            if not sender_ids:
                return jsonify({"requests": []})

            users = supabase.table("users") \
                .select("id, username, first_name, last_name") \
                .in_("id", sender_ids) \
                .execute()

            return jsonify({"requests": [
                {
                    "id": u["id"],
                    "username": u["username"],
                    "name": get_full_name(u),
                    "handle": f"@{u['username']}" if u.get("username") else "",
                    "initials": get_initials(get_full_name(u)),
                }
                for u in (users.data or [])
            ]})
        except Exception as e:
            return jsonify({"requests": [], "error": str(e)})

    @app.route("/friend/accept", methods=["POST"])
    @app.route("/api/friend-accept", methods=["POST"])
    def accept_friend():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json() or {}
        sender_id = data.get("sender_id") or data.get("requester_id")
        if not sender_id:
            return jsonify({"error": "Missing sender_id / requester_id"}), 400
        try:
            supabase.table("friendships") \
                .update({"status": "accepted"}) \
                .eq("user_id", str(sender_id)) \
                .eq("friend_id", str(session["user_id"])) \
                .execute()
            return jsonify({"status": "accepted"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/friend/reject", methods=["POST"])
    @app.route("/api/friend-reject", methods=["POST"])
    def reject_friend():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json() or {}
        sender_id = data.get("sender_id") or data.get("requester_id")
        if not sender_id:
            return jsonify({"error": "Missing sender_id / requester_id"}), 400
        try:
            supabase.table("friendships") \
                .delete() \
                .eq("user_id", str(sender_id)) \
                .eq("friend_id", str(session["user_id"])) \
                .execute()
            return jsonify({"status": "rejected"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/insights/friends-activity")
    def friends_activity():
        if "user_id" not in session:
            return jsonify({"activity": []})

        uid = str(session["user_id"])

        try:
            f1 = supabase.table("friendships").select("friend_id") \
                .eq("user_id", uid).eq("status", "accepted").execute()
            f2 = supabase.table("friendships").select("user_id") \
                .eq("friend_id", uid).eq("status", "accepted").execute()
        except Exception as e:
            return jsonify({"activity": [], "debug": f"friendships query failed: {e}"})

        friend_ids = list({r["friend_id"] for r in (f1.data or [])} |
                          {r["user_id"] for r in (f2.data or [])})

        if not friend_ids:
            return jsonify({"activity": [], "debug": "no accepted friends found"})

        try:
            activity_res = supabase.table("followed_insights") \
                .select("user_id, title, badges, created_at") \
                .in_("user_id", friend_ids) \
                .limit(20) \
                .execute()
        except Exception as e:
            return jsonify({"activity": [], "debug": f"followed_insights query failed: {e}"})

        rows = activity_res.data or []
        if not rows:
            return jsonify({"activity": [], "debug": "friends have not followed anything yet"})

        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)

        try:
            unique_ids = list({r["user_id"] for r in rows})
            users_res = supabase.table("users") \
                .select("id, username") \
                .in_("id", unique_ids) \
                .execute()
            id_to_username = {str(u["id"]): u["username"] for u in (users_res.data or [])}
        except Exception:
            id_to_username = {}

        result = [{
            "username": id_to_username.get(str(r["user_id"]), "Someone"),
            "title": r.get("title", ""),
            "badges": r.get("badges", ""),
            "created_at": r.get("created_at", "")
        } for r in rows]

        return jsonify({"activity": result})

    @app.route("/insights/follow", methods=["POST"])
    def follow_insight():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json()
        item_id = data.get("item_id")
        title = data.get("title", "")
        badges = data.get("badges", "")
        try:
            supabase.table("followed_insights").upsert({
                "user_id": str(session["user_id"]),
                "item_id": item_id,
                "title": title,
                "badges": badges
            }).execute()
            return jsonify({"status": "followed"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/insights/unfollow", methods=["POST"])
    def unfollow_insight():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json()
        item_id = data.get("item_id")
        try:
            supabase.table("followed_insights").delete() \
                .eq("user_id", str(session["user_id"])) \
                .eq("item_id", item_id) \
                .execute()
            return jsonify({"status": "unfollowed"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/insights/followed")
    def get_followed_insights():
        if "user_id" not in session:
            return jsonify({"items": []})
        try:
            result = supabase.table("followed_insights") \
                .select("item_id, title, badges") \
                .eq("user_id", str(session["user_id"])) \
                .execute()
            return jsonify({"items": result.data or []})
        except Exception:
            return jsonify({"items": []})

    @app.route("/matchmaking")
    def matchmaking():
        if "user_id" not in session:
            return redirect(url_for("auth"))

        current_user_id = int(get_current_user_id())
        friend_requests = get_friend_requests_for_user(current_user_id)
        friends_list = get_friends_for_user(current_user_id)

        return render_template(
            "matchmaking.html",
            friend_requests=friend_requests,
            friends_list=friends_list
        )

    @app.route("/message")
    def message():
        return render_template("message.html")
    
    # Push subscription storage remains available when the client registers a web push endpoint.

    @app.route("/api/save_subscription", methods=["POST"])
    def save_subscription():

        if "user_id" not in session:
            return {"error": "not logged in"}, 401

        subscription = request.json

        supabase.table("push_subscriptions").insert({
            "user_id": session["user_id"],
            "subscription": subscription
        }).execute()

        return {"status": "saved"}

    @app.route("/blocked-accounts")
    def blocked_accounts():
        return render_template("blocked_accounts.html")

    @app.route("/report")
    def report():
        return render_template("report.html")

    @app.route("/spotify/test-top-artists")
    def spotify_test_top_artists():
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "")

        if not token:
            return jsonify({"error": "Missing Spotify token"}), 401

        r = requests.get(
            "https://api.spotify.com/v1/me/top/artists",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 20, "time_range": "medium_term"}
        )

        if r.status_code != 200:
            return jsonify({"error": "Spotify error", "status": r.status_code, "body": r.text}), r.status_code

        data = r.json()

        artists = []
        for a in data.get("items", []):
            image = a["images"][0]["url"] if a.get("images") else None
            artists.append({"id": a["id"], "name": a["name"], "image": image})

        return jsonify(artists)
    
    # Messaging endpoints persist rows in Supabase for basic send flows during demos.

    @app.route("/api/send_message", methods=["POST"])
    def send_message():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401

        data = request.json
        recipient_id = data.get("recipient_id")
        body = data.get("body")

        if not recipient_id or not body:
            return jsonify({"error": "Missing data"}), 400

        result = supabase.table("messages").insert({
            "sender_id": int(session["user_id"]),
            "recipient_id": int(recipient_id),
            "body": body
        }).execute()

        return jsonify(result.data)


    @app.route("/api/get_messages/<recipient_id>")
    def get_messages(recipient_id):
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401

        user_id = session["user_id"]
        recipient_id = int(recipient_id)

        result = supabase.table("messages") \
            .select("*") \
            .or_(f"and(sender_id.eq.{user_id},recipient_id.eq.{recipient_id}),and(sender_id.eq.{recipient_id},recipient_id.eq.{user_id})") \
            .order("created_at") \
            .execute()

        return jsonify(result.data)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)