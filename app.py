from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import re
import requests

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


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

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        # Offline fallback
        session["user_id"] = "test_user_123"
        session["username"] = username
        return redirect(url_for("home"))

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
        return render_template("weekly_insights.html")

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
                .select("id, username") \
                .in_("id", sender_ids) \
                .execute()

            return jsonify({"requests": [
                {"id": u["id"], "username": u["username"]}
                for u in (users.data or [])
            ]})
        except Exception as e:
            return jsonify({"requests": [], "error": str(e)})

    @app.route("/friend/accept", methods=["POST"])
    def accept_friend():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json()
        sender_id = data.get("sender_id")
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
    def reject_friend():
        if "user_id" not in session:
            return jsonify({"error": "Not logged in"}), 401
        data = request.get_json()
        sender_id = data.get("sender_id")
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
    
    # ============================================================
    # Push Notifications API (Placeholder)
    # ============================================================

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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)