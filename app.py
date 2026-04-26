from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os, re, requests, json
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Supabase — loaded if credentials are present, otherwise app runs in offline mode
supabase = None
try:
    from supabase import create_client
    _sb_url = os.getenv("SUPABASE_URL")
    _sb_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if _sb_url and _sb_key:
        supabase = create_client(_sb_url, _sb_key)
except Exception:
    pass

# =========================
# EVENT DATA
# =========================
EVENTS = {
    "daniel-caesar": {
        "title": "Daniel Caesar — NEVER ENOUGH Tour",
        "artist": "Daniel Caesar",
        "genre": "R&B / Neo-Soul",
        "date": "Nov 23, 2025",
        "location": "SoFi Stadium, Los Angeles",
        "description": "Daniel Caesar brings his Never Enough tour to SoFi Stadium for one night only. Expect deep cuts, fan favourites, and a setlist spanning his entire discography.",
        "image": "images/placeholder_caser.png",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/danielcaesar/",
            "spotify": "https://open.spotify.com/artist/20wkVLutqVOYrc0kxFs7rA"
        }
    },
    "flawed-mangoes": {
        "title": "Flawed Mangoes — Debut Headline Show",
        "artist": "Flawed Mangoes",
        "genre": "Alternative / Indie R&B",
        "date": "Sep 28, 2025",
        "location": "EchoPlex, Los Angeles",
        "description": "Rising indie-R&B act Flawed Mangoes plays their first ever headline show at the iconic EchoPlex. Limited capacity — don't sleep on this one.",
        "image": "images/placeholder_flawed.jpg",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/",
            "spotify": "https://open.spotify.com/"
        }
    },
    "benson-boone": {
        "title": "Benson Boone — Beautiful Things World Tour",
        "artist": "Benson Boone",
        "genre": "Pop / Alternative",
        "date": "Dec 25, 2025",
        "location": "YouTube Theater, Inglewood",
        "description": "Benson Boone closes out his blockbuster world tour with a special holiday show in LA. Fresh off a record-breaking year, this one promises to be unforgettable.",
        "image": "images/placeholder_benson.jpg",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/bensonboone/",
            "spotify": "https://open.spotify.com/artist/22vgEDb5hykfaTwLuskFGD"
        }
    },
    "tyler-the-creator": {
        "title": "Tyler, The Creator — CHROMAKOPIA World Tour",
        "artist": "Tyler, The Creator",
        "genre": "Hip-Hop / Neo-Psychedelic",
        "date": "Jan 18, 2026",
        "location": "Kia Forum, Inglewood",
        "description": "Tyler brings the full CHROMAKOPIA production to the Kia Forum. Expect elaborate stage design, live instrumentation, and a career-spanning setlist.",
        "image": "images/event_placeholder.png",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/feliciathegoat/",
            "spotify": "https://open.spotify.com/artist/4V8LLVI7d68sQt3NaEab46"
        }
    },
    "sza": {
        "title": "SZA — SOS Deluxe Live",
        "artist": "SZA",
        "genre": "R&B / Alternative",
        "date": "Feb 7, 2026",
        "location": "Crypto.com Arena, Los Angeles",
        "description": "SZA performs the full SOS Deluxe album live for the very first time, with new tracks, surprise guests, and her biggest production yet.",
        "image": "images/event_placeholder.png",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/sza/",
            "spotify": "https://open.spotify.com/artist/7tYKF4w9nC0nq9CsPZTHyP"
        }
    },
    "kendrick-lamar": {
        "title": "Kendrick Lamar — The Pop Out: LA Edition",
        "artist": "Kendrick Lamar",
        "genre": "Hip-Hop",
        "date": "Mar 15, 2026",
        "location": "Dodger Stadium, Los Angeles",
        "description": "Following his Super Bowl halftime show, Kendrick Lamar returns to LA for a one-night stadium spectacle celebrating Compton and the culture.",
        "image": "images/event_placeholder.png",
        "ticket_url": "https://www.ticketmaster.com/",
        "socials": {
            "instagram": "https://www.instagram.com/kendricklamar/",
            "spotify": "https://open.spotify.com/artist/2YZyLoL8N0Wb9xBt1NhZWg"
        }
    },
}

# ============================================================
# FLASK APP FACTORY
# ============================================================

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET", "SUPER_SECRET_KEY")

    # ============================================================
    # HELPERS
    # ============================================================

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


    # ============================================================
    # ROUTES
    # ============================================================

    @app.route("/")
    def index():
        return redirect(url_for("home"))

    # ===== AUTH PAGE (shows login + signup forms) =====
    @app.route("/auth")
    def auth():
        # Change back to auth.html when auth is set up
        return render_template("auth.html")

    # ===== SIGNUP =====
    @app.route("/signup", methods=["POST"])
    def signup():
        first_name = request.form["firstName"]
        last_name = request.form["lastName"]
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]
        confirm = request.form["confirmPassword"]

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth"))

        if supabase:
            try:
                existing = supabase.table("users") \
                    .select("id") \
                    .or_(f"username.eq.{username},email.eq.{email}") \
                    .execute()
                if existing.data:
                    flash("Username or email already exists.", "error")
                    return redirect(url_for("auth"))

                password_hash = generate_password_hash(password)
                result = supabase.table("users").insert({
                    "first_name": first_name,
                    "last_name": last_name,
                    "username": username,
                    "email": email,
                    "password_hash": password_hash
                }).execute()
                user = result.data[0]
                session["user_id"] = str(user["id"])
                session["username"] = user["username"]
                return redirect(url_for("home"))
            except Exception as e:
                flash(f"Sign-up error: {e}", "error")
                return redirect(url_for("auth"))

        # Offline fallback
        session["user_id"] = "test_user_123"
        session["username"] = username
        return redirect(url_for("home"))


    # ===== LOGIN =====
    @app.route("/login", methods=["POST"])
    def login():
        identity = request.form["identity"]
        password = request.form["password"]

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

        # Offline fallback
        session.clear()
        session["user_id"] = "test_user_123"
        session["username"] = identity if identity else "test_user"
        return redirect(url_for("home"))


    # ===== LOGOUT =====
    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth"))

    # ===== HOME =====
    @app.route("/home")
    def home():
        # Auth check disabled for development - re-enable when Supabase is configured
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))

        username = session.get("username", "Guest")
        return render_template("home.html", username=username)


    # ===== PROFILE =====
    @app.route("/profile")
    def profile():
        # Auth check disabled for development - re-enable when Supabase is configured
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))

        username = session.get("username", "Guest")
        slug = slugify(username)
        img_url = pick_user_image_by_slug(slug)
        favorite_ids = session.get("favorite_insights", [])
        followed_insights = [item for item in WEEKLY_INSIGHTS if item["id"] in favorite_ids]
        return render_template(
            "profile.html",
            img_url=img_url,
            display_name=username,
            followed_insights=followed_insights

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

    # ===== TEST ROUTE (Optional) =====
    @app.route("/test_supabase")
    def test_supabase():
        # Supabase code commented out for testing
        # data = supabase.table("profiles").select("*").execute()
        # return {"data": data.data, "error": data.error}
        return {"data": [], "error": "Supabase not configured - test route disabled"}

    # ===== OTHER ROUTES =====
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

    @app.route("/settings")
    def settings():
        # Auth check disabled for development - re-enable when Supabase is configured
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))
        return render_template("settings.html")

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
    
    @app.route("/weekly-insights/favorite/<insight_id>", methods=["POST"])
    def toggle_favorite_insight(insight_id):
        favorites = session.get("favorite_insights", [])
        if insight_id in favorites:
            favorites.remove(insight_id)
        else:
            favorites.append(insight_id)
            insight = next((i for i in WEEKLY_INSIGHTS if i["id"] == insight_id), None)
            if insight:
                _append_activity({
                    "user_id": session.get("user_id", "guest"),
                    "username": session.get("username", "someone"),
                    "type": "liked_insight",
                    "title": insight["title"],
                    "time": "Just now",
                })
        session["favorite_insights"] = favorites
        return redirect(url_for("weekly_insights"))
    @app.route("/matchmaking")
    def matchmaking():
        return render_template("matchmaking.html")

    @app.route("/message")
    def message():
        return render_template("message.html")

    @app.route("/blocked-accounts")
    def blocked_accounts():
        return render_template("blocked_accounts.html")

    @app.route("/report")
    def report():
        return render_template("report.html")

    @app.route("/chatbot")
    def chatbot():
        # Auth check disabled for development - re-enable when Supabase is configured
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))
        return render_template("chatbot.html")

    @app.route("/onboarding-quiz")
    def onboarding_quiz():
        # Auth check disabled for development - re-enable when Supabase is configured
        # if "user_id" not in session:
        #     return redirect(url_for("auth"))
        return render_template("onboarding_quiz.html")


    # ===== Spotify Retrieval =====
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

    # ===== SEARCH USERS =====
    @app.get("/search_users")
    def search_users():
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"users": []})
        current_uid = str(session.get("user_id", ""))
        if supabase:
            try:
                res = supabase.table("users") \
                    .select("id, username, first_name, last_name") \
                    .or_(f"username.ilike.%{q}%,first_name.ilike.%{q}%,last_name.ilike.%{q}%") \
                    .limit(20).execute()
                users = []
                for u in (res.data or []):
                    if str(u.get("id")) == current_uid:
                        continue
                    fn = (u.get("first_name") or "").strip()
                    ln = (u.get("last_name") or "").strip()
                    name = f"{fn} {ln}".strip() or u.get("username", "")
                    users.append({
                        "id": str(u["id"]),
                        "username": u.get("username"),
                        "name": name,
                        "handle": f"@{u.get('username')}",
                        "initials": ((fn[:1] + ln[:1]).upper() or "U"),
                    })
                return jsonify({"users": users})
            except Exception:
                pass
        q_lo = q.lower()
        users = []
        for u in MOCK_USERS:
            name = f"{u['first_name']} {u['last_name']}"
            if q_lo in name.lower() or q_lo in u["username"].lower():
                users.append({
                    "id": u["id"], "username": u["username"], "name": name,
                    "handle": f"@{u['username']}",
                    "initials": (u["first_name"][0] + u["last_name"][0]).upper(),
                })
        return jsonify({"users": users})

    # ===== SUGGESTED USERS =====
    MOCK_USERS = [
        {"id": "u1", "username": "jxmxs",      "first_name": "James",  "last_name": "Park"},
        {"id": "u2", "username": "nova.beats",  "first_name": "Nova",   "last_name": "Williams"},
        {"id": "u3", "username": "kaito_mx",    "first_name": "Kaito",  "last_name": "Morales"},
        {"id": "u4", "username": "sxnrise",     "first_name": "Serena", "last_name": "Okafor"},
        {"id": "u5", "username": "blvd.andre",  "first_name": "Andre",  "last_name": "Bennett"},
    ]

    def _get_connected_ids(uid):
        """Return set of user IDs already connected (any status) with uid."""
        if not supabase or not uid:
            return set()
        try:
            r1 = supabase.table("friendships").select("friend_id") \
                .eq("user_id", str(uid)).execute()
            r2 = supabase.table("friendships").select("user_id") \
                .eq("friend_id", str(uid)).execute()
            return {str(r["friend_id"]) for r in (r1.data or [])} | \
                   {str(r["user_id"])   for r in (r2.data or [])}
        except Exception:
            return set()

    def _get_accepted_friend_ids(uid):
        """Return set of user IDs with an accepted friendship with uid."""
        if not supabase or not uid:
            return set()
        try:
            r1 = supabase.table("friendships").select("friend_id") \
                .eq("user_id", str(uid)).eq("status", "accepted").execute()
            r2 = supabase.table("friendships").select("user_id") \
                .eq("friend_id", str(uid)).eq("status", "accepted").execute()
            return {str(r["friend_id"]) for r in (r1.data or [])} | \
                   {str(r["user_id"])   for r in (r2.data or [])}
        except Exception:
            return set()

    def _fmt_user(u, connected_ids):
        uid = str(u["id"])
        fn  = (u.get("first_name") or "").strip()
        ln  = (u.get("last_name")  or "").strip()
        name = f"{fn} {ln}".strip() or u.get("username") or "User"
        inits = ((fn[:1] + ln[:1]).upper()) or (u.get("username") or "U")[0].upper()
        return {
            "id": uid,
            "username": u.get("username") or "",
            "name": name,
            "handle": f"@{u.get('username') or uid}",
            "initials": inits,
            "requested": uid in connected_ids,
        }

    @app.get("/api/suggested-users")
    def suggested_users():
        current_uid = str(session.get("user_id", ""))
        connected = _get_connected_ids(current_uid)
        if supabase:
            try:
                res = supabase.table("users") \
                    .select("id, username, first_name, last_name") \
                    .limit(30).execute()
                users = [_fmt_user(u, connected)
                         for u in (res.data or [])
                         if str(u["id"]) != current_uid]
                return jsonify({"users": users})
            except Exception:
                pass
        # offline fallback
        users = []
        for u in MOCK_USERS:
            name = f"{u['first_name']} {u['last_name']}"
            users.append({
                "id": u["id"], "username": u["username"], "name": name,
                "handle": f"@{u['username']}",
                "initials": (u["first_name"][0] + u["last_name"][0]).upper(),
                "requested": u["id"] in connected,
            })
        return jsonify({"users": users})

    @app.get("/api/friend-requests")
    def api_friend_requests():
        if supabase:
            try:
                uid = str(session.get("user_id", ""))
                if not uid:
                    return jsonify({"requests": []})
                # rows where someone sent a request TO the current user
                res = supabase.table("friendships") \
                    .select("user_id") \
                    .eq("friend_id", uid) \
                    .eq("status", "pending") \
                    .execute()
                sender_ids = [str(r["user_id"]) for r in (res.data or [])]
                if not sender_ids:
                    return jsonify({"requests": []})
                users_res = supabase.table("users") \
                    .select("id, username, first_name, last_name") \
                    .in_("id", sender_ids).execute()
                reqs = [_fmt_user(u, set()) for u in (users_res.data or [])]
                return jsonify({"requests": reqs})
            except Exception:
                pass
        return jsonify({"requests": []})

    @app.post("/api/add-friend")
    def api_add_friend():
        data = request.get_json() or {}
        friend_id = str(data.get("friend_id", ""))
        if not friend_id:
            return jsonify({"error": "Missing friend_id"}), 400
        uid = str(session.get("user_id", ""))
        if supabase and uid:
            try:
                supabase.table("friendships").upsert({
                    "user_id": uid,
                    "friend_id": friend_id,
                    "status": "pending"
                }).execute()
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"status": "requested"})

    @app.post("/api/friend-accept")
    def api_friend_accept():
        data = request.get_json() or {}
        rid = str(data.get("requester_id", ""))
        uid = str(session.get("user_id", ""))
        if supabase and uid and rid:
            try:
                supabase.table("friendships") \
                    .update({"status": "accepted"}) \
                    .eq("user_id", rid) \
                    .eq("friend_id", uid) \
                    .execute()
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"status": "accepted"})

    @app.post("/api/friend-reject")
    def api_friend_reject():
        data = request.get_json() or {}
        rid = str(data.get("requester_id", ""))
        uid = str(session.get("user_id", ""))
        if supabase and uid and rid:
            try:
                supabase.table("friendships") \
                    .delete() \
                    .eq("user_id", rid) \
                    .eq("friend_id", uid) \
                    .execute()
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"status": "rejected"})

    # ===== INVITE =====
    @app.get("/invite")
    def invite():
        return redirect(url_for("auth"))

    # ===== FRIENDS ACTIVITY =====
    @app.get("/api/friends-activity")
    def api_friends_activity():
        current_uid = str(session.get("user_id", ""))
        friend_ids = _get_accepted_friend_ids(current_uid)
        log = _load_activity()
        activity = [e for e in log if str(e.get("user_id")) in friend_ids]
        return jsonify({"activity": activity[:20]})

    # ===== EVENT PHOTO FEED =====
    @app.get("/api/event-photos")
    def get_event_photos():
        import json as _json
        photos_dir = os.path.join(app.static_folder, "uploads", "event-photos")
        os.makedirs(photos_dir, exist_ok=True)
        meta = os.path.join(photos_dir, "metadata.json")
        all_photos = _json.loads(open(meta).read()) if os.path.exists(meta) else []
        current_uid = str(session.get("user_id", ""))
        friend_ids = _get_accepted_friend_ids(current_uid)
        # Show own photos + friends' photos
        allowed = friend_ids | {current_uid}
        if allowed and current_uid:
            photos = [p for p in all_photos if str(p.get("user_id", "")) in allowed]
        else:
            photos = all_photos
        return jsonify({"photos": photos})

    @app.post("/api/event-photos")
    def upload_event_photo():
        import json as _json, time as _time, uuid as _uuid
        file = request.files.get("photo")
        caption = (request.form.get("caption") or "").strip()
        if not file or file.filename == "":
            return jsonify({"error": "No photo"}), 400
        _, ext = os.path.splitext(file.filename.lower())
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            return jsonify({"error": "Invalid type"}), 400

        photos_dir = os.path.join(app.static_folder, "uploads", "event-photos")
        os.makedirs(photos_dir, exist_ok=True)
        filename = f"{int(_time.time())}_{_uuid.uuid4().hex[:8]}{ext}"
        file.save(os.path.join(photos_dir, filename))

        meta = os.path.join(photos_dir, "metadata.json")
        photos = _json.loads(open(meta).read()) if os.path.exists(meta) else []
        photos.insert(0, {
            "url": f"/static/uploads/event-photos/{filename}",
            "caption": caption,
            "username": session.get("username", "Guest"),
            "user_id": str(session.get("user_id", "")),
            "time": "Just now",
        })
        with open(meta, "w") as fh:
            _json.dump(photos, fh)

        _append_activity({
            "user_id": session.get("user_id", "guest"),
            "username": session.get("username", "someone"),
            "type": "posted_photo",
            "caption": caption or "Event photo",
            "photo_url": f"/static/uploads/event-photos/{filename}",
            "time": "Just now",
        })

        return jsonify({"status": "uploaded", "url": f"/static/uploads/event-photos/{filename}"})

    return app






app = create_app()

if __name__ == "__main__":
    app.run(debug=True)