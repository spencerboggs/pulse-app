from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import os, re, requests
import base64
import hashlib


# ============================================================
# ENVIRONMENT LOADING
# ============================================================

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# FLASK APP FACTORY
# ============================================================

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET", "SUPER_SECRET_KEY")

    # ============================================================
    # SPOTIFY HELPERS
    # ============================================================

    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_REDIRECT_URI = os.getenv(
        "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/callback"
    )
    SPOTIFY_SCOPES = "user-top-read user-read-private"

    def _b64url(data: bytes) -> str:
        """URL-safe base64 encode without padding (PKCE)."""
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    def _make_pkce():
        verifier = _b64url(os.urandom(32))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        return verifier, challenge

    def _save_spotify_tokens(user_id, token_json):
        """Persist Spotify token + profile to the users row.

        token_json is the JSON returned by Spotify's /api/token endpoint.
        Also calls /v1/me to get the spotify user id + display name so we
        can show 'Connected as X' in the UI.
        """
        access_token = token_json["access_token"]
        refresh_token = token_json.get("refresh_token")
        expires_in = int(token_json.get("expires_in", 3600))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Look up the spotify profile so we know which account this is.
        me = requests.get(
            "https://api.spotify.com/v1/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        spotify_user_id = None
        spotify_display_name = None
        if me.status_code == 200:
            me_json = me.json()
            spotify_user_id = me_json.get("id")
            spotify_display_name = me_json.get("display_name") or me_json.get("id")

        update_row = {
            "spotify_access_token": access_token,
            "spotify_token_expires_at": expires_at.isoformat(),
            "spotify_connected_at": datetime.now(timezone.utc).isoformat(),
        }
        # Spotify only returns refresh_token on the initial exchange; preserve
        # the existing one on subsequent refreshes if it's not re-sent.
        if refresh_token:
            update_row["spotify_refresh_token"] = refresh_token
        if spotify_user_id:
            update_row["spotify_user_id"] = spotify_user_id
        if spotify_display_name:
            update_row["spotify_display_name"] = spotify_display_name

        supabase.table("users").update(update_row).eq("id", user_id).execute()
        return spotify_user_id, spotify_display_name

    def _get_valid_spotify_token(user_id):
        """Return a non-expired access token for this user, refreshing if needed.

        Returns None if the user has no Spotify connection or refresh fails.
        """
        res = (
            supabase.table("users")
            .select(
                "spotify_access_token,"
                "spotify_refresh_token,"
                "spotify_token_expires_at"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )
        if not res.data:
            return None

        access_token = res.data.get("spotify_access_token")
        refresh_token = res.data.get("spotify_refresh_token")
        expires_at_str = res.data.get("spotify_token_expires_at")

        if not access_token:
            return None

        # If the token is still good for >60s, use it as-is.
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(
                    expires_at_str.replace("Z", "+00:00")
                )
                if expires_at > datetime.now(timezone.utc) + timedelta(seconds=60):
                    return access_token
            except ValueError:
                pass  # bad timestamp, fall through and try to refresh

        # Token expired (or unknown expiry) — try to refresh.
        if not refresh_token:
            return access_token  # last resort: caller will get 401 and re-auth

        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": SPOTIFY_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        if r.status_code != 200:
            return None

        new_json = r.json()
        new_access = new_json["access_token"]
        new_expires = datetime.now(timezone.utc) + timedelta(
            seconds=int(new_json.get("expires_in", 3600))
        )
        update_row = {
            "spotify_access_token": new_access,
            "spotify_token_expires_at": new_expires.isoformat(),
        }
        # Spotify may rotate the refresh token.
        if new_json.get("refresh_token"):
            update_row["spotify_refresh_token"] = new_json["refresh_token"]
        supabase.table("users").update(update_row).eq("id", user_id).execute()
        return new_access

    # ============================================================
    # SPOTIFY ROUTES
    # ============================================================

    @app.route("/spotify/save-artists")
    def save_artists():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in to Pulse"}), 401

        token = _get_valid_spotify_token(user_id)
        if not token:
            return jsonify({"error": "Not connected to Spotify"}), 401

        r = requests.get(
            url="https://api.spotify.com/v1/me/top/artists",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 20, "time_range": "medium_term"},
            timeout=10,
        )

        if r.status_code != 200:
            return jsonify({"error": "Spotify error", "status": r.status_code, "body": r.text}), r.status_code

        artists = r.json().get("items", [])

        saved = 0
        for a in artists:
            row = {
                "user_id": user_id,
                "spotify_id": a["id"],
                "name": a["name"],
                "image": a["images"][0]["url"] if a.get("images") else None
            }

            supabase.table("user_top_artists").upsert(row).execute()
            saved += 1

        return jsonify({"status": "saved", "count": saved})

    @app.route("/search/artists")
    def search_artists():
        query = request.args.get("q", "").strip()

        if not query:
            return jsonify([])

        res = (
            supabase.table("user_top_artists")
            .select("spotify_id,name,image")
            .ilike("name", f"%{query}%")
            .limit(20)
            .execute()
        )

        # remove duplicates by spotify_id
        unique_artists = {}
        for a in res.data:
            unique_artists[a["spotify_id"]] = {
                "spotify_id": a["spotify_id"],
                "name": a["name"],
                "image": a.get("image")
            }



        return jsonify(list(unique_artists.values()))

    @app.route("/spotify/top-artists")
    def spotify_top_artists():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in to Pulse"}), 401

        token = _get_valid_spotify_token(user_id)
        if not token:
            return jsonify({"error": "Not connected to Spotify. Connect on your profile page."}), 401

        r = requests.get(
            "https://api.spotify.com/v1/me/top/artists",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 20, "time_range": "medium_term"},
            timeout=10,
        )

        if r.status_code != 200:
            return jsonify({"error": "Spotify error", "status": r.status_code, "body": r.text}), r.status_code

        data = r.json()

        artists = [
            {
                "id": a["id"],
                "name": a["name"],
                "image": a["images"][0]["url"] if a.get("images") else None
            }
            for a in data.get("items", [])
        ]
        return jsonify(artists)

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
            return url_for("static", filename=f"uploads/{latest}")

        return url_for("static", filename="images/profile_placeholder.png")

    # ============================================================
    # ROUTES
    # ============================================================

    @app.route("/")
    def index():
        return redirect(url_for("auth"))

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

        # Check if username or email exists
        existing = supabase.table("users") \
            .select("id") \
            .or_(f"username.eq.{username},email.eq.{email}") \
            .execute()

        if existing.data:
            flash("Username or email already exists.", "error")
            return redirect(url_for("auth"))

        password_hash = generate_password_hash(password)

        result = supabase.table("users").insert({
            "username": username,
            "email": email,
            "password_hash": password_hash
        }).execute()

        user = result.data[0]

        # Login user
        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect(url_for("home"))


    # ===== LOGIN =====
    @app.route("/login", methods=["POST"])
    def login():
        identity = request.form["identity"]
        password = request.form["password"]

        query = supabase.table("users") \
            .select("*") \
            .or_(f"username.eq.{identity},email.eq.{identity}") \
            .limit(1) \
            .execute()

        user = query.data[0] if query.data else None

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "error")
            return redirect(url_for("auth"))

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect(url_for("home"))


    # ===== LOGOUT =====
    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth"))

    # ===== HOME =====
    @app.route("/home")
    def home():
        if "user_id" not in session:
            return redirect(url_for("auth"))

        return render_template("home.html", username=session["username"])


    # ===== PROFILE =====
    @app.route("/profile")
    def profile():
        if "user_id" not in session:
            return redirect(url_for("auth"))

        slug = slugify(session["username"])
        img_url = pick_user_image_by_slug(slug)

        return render_template(
            "profile.html",
            img_url=img_url,
            display_name=session["username"]
        )


    @app.route("/u/<path:username>")
    def user_profile(username):
        slug = slugify(username)
        img_url = pick_user_image_by_slug(slug)
        return render_template("profile_view.html", img_url=img_url, display_name=username)

    # ===== TEST ROUTE (Optional) =====
    @app.route("/test_supabase")
    def test_supabase():
        data = supabase.table("profiles").select("*").execute()
        return {"data": data.data, "error": data.error}

    # ===== OTHER ROUTES =====
    @app.route("/events")
    def events():
        return render_template("events.html")

    @app.route("/concert-map")
    def concert_map():
        return render_template("concert_map.html")

    @app.route("/settings")
    def settings():
        return render_template("settings.html")

    @app.route("/weekly-insights")
    def weekly_insights():
        return render_template("weekly_insights.html")

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

    @app.route("/search/similar-users-by-artist/<spotify_artist_id>")
    def similar_users_by_artist(spotify_artist_id):
        current_user_id = session.get("user_id")

        if not current_user_id:
            return jsonify({"error": "Not logged in"}), 401

        # Find all users who have this artist
        artist_users = (
            supabase.table("user_top_artists")
            .select("user_id")
            .eq("spotify_id", spotify_artist_id)
            .neq("user_id", current_user_id)
            .execute()
        )

        if not artist_users.data:
            return jsonify([])

        matched_users = []
        for row in artist_users.data:
            other_user_id = row["user_id"]

            # Get current user's artists
            current_artists_res = (
                supabase.table("user_top_artists")
                .select("spotify_id")
                .eq("user_id", current_user_id)
                .execute()
            )

            # Get other user's artists
            other_artists_res = (
                supabase.table("user_top_artists")
                .select("spotify_id")
                .eq("user_id", other_user_id)
                .execute()
            )

            current_artist_ids = {a["spotify_id"] for a in current_artists_res.data}
            other_artist_ids = {a["spotify_id"] for a in other_artists_res.data}

            similarity_score = len(current_artist_ids & other_artist_ids)

            user_res = (
                supabase.table("users")
                .select("id,username,email")
                .eq("id", other_user_id)
                .single()
                .execute()
            )

            if user_res.data:
                matched_users.append({
                    "user_id": user_res.data["id"],
                    "username": user_res.data["username"],
                    "email": user_res.data["email"],
                    "similarity_score": similarity_score
                })

        matched_users.sort(key=lambda x: x["similarity_score"], reverse=True)
        return jsonify(matched_users)

    # ===== Spotify Retrieval =====
    # Test endpoint that allows manual API calls using a Bearer token
    # from the request header instead of the Flask session.
    # Useful for Postman testing or debugging OAuth flow.
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
        # If Spotify responds with an error, forward details to the client

        if r.status_code != 200:
            return jsonify({"error": "Spotify error", "status": r.status_code, "body": r.text}), r.status_code

        data = r.json()

        artists = []
        for a in data.get("items", []):
            image = a["images"][0]["url"] if a.get("images") else None
            artists.append({"id": a["id"], "name": a["name"], "image": image})

        return jsonify(artists)

    # ============================================================
    # SPOTIFY OAUTH (PKCE) + ACCOUNT CONNECTION
    # ============================================================

    # Step 1 of 2: send the user to Spotify's consent page.
    # Requires the user to already be logged into Pulse so we know
    # which account to attach the Spotify connection to.
    @app.route("/spotify/login")
    def spotify_login():
        if "user_id" not in session:
            flash("Log in to Pulse first, then connect Spotify.", "error")
            return redirect(url_for("auth"))

        verifier, challenge = _make_pkce()
        session["spotify_verifier"] = verifier

        auth_url = (
            "https://accounts.spotify.com/authorize"
            f"?client_id={SPOTIFY_CLIENT_ID}"
            f"&response_type=code"
            f"&redirect_uri={requests.utils.quote(SPOTIFY_REDIRECT_URI, safe='')}"
            f"&scope={requests.utils.quote(SPOTIFY_SCOPES)}"
            f"&code_challenge_method=S256"
            f"&code_challenge={challenge}"
        )
        return redirect(auth_url)

    # Step 2 of 2: Spotify redirects back here with ?code=...
    # We exchange the code for tokens, fetch the spotify profile,
    # persist everything to the users table, then send the user
    # back to their profile page.
    @app.route("/callback")
    def spotify_callback():
        user_id = session.get("user_id")
        if not user_id:
            flash("Your session expired. Log in and try again.", "error")
            return redirect(url_for("auth"))

        code = request.args.get("code")
        if not code:
            err = request.args.get("error", "no_code")
            flash(f"Spotify did not return an auth code ({err}).", "error")
            return redirect(url_for("profile"))

        verifier = session.pop("spotify_verifier", None)
        if not verifier:
            flash("Missing PKCE verifier — please retry the connection.", "error")
            return redirect(url_for("profile"))

        token_res = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "client_id": SPOTIFY_CLIENT_ID,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        if token_res.status_code != 200:
            flash(f"Spotify token exchange failed: {token_res.text}", "error")
            return redirect(url_for("profile"))

        token_json = token_res.json()

        # Persist tokens + spotify profile info to the users row.
        try:
            _save_spotify_tokens(user_id, token_json)
        except Exception as e:
            flash(f"Could not save Spotify connection: {e}", "error")
            return redirect(url_for("profile"))

        return redirect(url_for("profile") + "?spotify=connected")

    # JSON endpoint the profile page polls on load to render either
    # the "Connect" button or the "Connected as X" state.
    @app.route("/spotify/status")
    def spotify_status():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"connected": False, "reason": "not_logged_in"}), 401

        res = (
            supabase.table("users")
            .select(
                "spotify_user_id,"
                "spotify_display_name,"
                "spotify_connected_at"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )
        data = res.data or {}
        connected = bool(data.get("spotify_user_id"))
        return jsonify({
            "connected": connected,
            "spotify_user_id": data.get("spotify_user_id"),
            "spotify_display_name": data.get("spotify_display_name"),
            "connected_at": data.get("spotify_connected_at"),
        })

    # Clears Spotify columns on the user row. POST-only so it's not
    # triggerable by a stray <img src> or pre-fetcher.
    @app.route("/spotify/disconnect", methods=["POST"])
    def spotify_disconnect():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401

        supabase.table("users").update({
            "spotify_user_id": None,
            "spotify_display_name": None,
            "spotify_access_token": None,
            "spotify_refresh_token": None,
            "spotify_token_expires_at": None,
            "spotify_connected_at": None,
        }).eq("id", user_id).execute()

        # Also clear the legacy session token if present.
        session.pop("spotify_access_token", None)
        session.pop("spotify_verifier", None)

        return jsonify({"status": "disconnected"})

    @app.route("/connections/create", methods=["POST"])
    def create_connection():
        current_user_id = session.get("user_id")
        data = request.get_json()

        if not current_user_id:
            return jsonify({"error": "Not logged in"}), 401

        match_user_id = data.get("match_user_id")
        similarity_score = data.get("similarity_score", 0)

        if not match_user_id:
            return jsonify({"error": "Missing match_user_id"}), 400

        row = {
            "user_id": current_user_id,
            "match_user_id": match_user_id,
            "similarity_score": similarity_score
        }

        supabase.table("connections").upsert(row).execute()

        return jsonify({"status": "connection created"})

    # Demo route: returns seeded top artists for a suggested user
    @app.route("/demo/user-artists/<username>")
    def demo_user_artists(username):
        demo_artists = {
            "lenaverse": [
                "Taylor Swift", "SZA", "Lana Del Rey", "Phoebe Bridgers", "Clairo",
                "The Marías", "Beabadoobee", "Gracie Abrams", "Olivia Rodrigo", "Mitski"
            ],
            "c0debycaleb": [
                "Drake", "Travis Scott", "Kendrick Lamar", "Future", "J. Cole",
                "Metro Boomin", "The Weeknd", "21 Savage", "Lil Uzi Vert", "Don Toliver"
            ],
            "itsmayac": [
                "NewJeans", "TWICE", "BLACKPINK", "LE SSERAFIM", "IVE",
                "aespa", "Red Velvet", "IU", "NCT 127", "Stray Kids"
            ],
            "danthebuilder": [
                "Linkin Park", "Bring Me The Horizon", "System of a Down", "Slipknot", "Deftones",
                "Three Days Grace", "Breaking Benjamin", "Avenged Sevenfold", "Papa Roach", "Paramore"
            ],
            "elinavdev": [
                "Arctic Monkeys", "The 1975", "Tame Impala", "The Strokes", "Wallows",
                "Cigarettes After Sex", "Joji", "Mac DeMarco", "TV Girl", "Rex Orange County"
            ],
            "zoeyk.dev": [
                "Bad Bunny", "Kali Uchis", "Karol G", "ROSALÍA", "J Balvin",
                "Rauw Alejandro", "Feid", "Peso Pluma", "Shakira", "Ozuna"
            ],
            "norapixel": [
                "Coldplay", "OneRepublic", "Imagine Dragons", "Adele", "Ed Sheeran",
                "Billie Eilish", "Shawn Mendes", "Dua Lipa", "Harry Styles", "Sam Smith"
            ]
        }

        return jsonify({
            "username": username,
            "artists": demo_artists.get(username, ["No artists found"])
        })

    @app.route("/artists/overview")
    def artists_overview():
        # Pull artist rows from the database
        res = (
            supabase.table("user_top_artists")
            .select("artist_id,name,user_id")
            .order("name")
            .execute()
        )

        rows = res.data if res.data else []

        if not rows:
            return jsonify([])

        # Get all users so we can map user_id -> username
        users_res = (
            supabase.table("users")
            .select("id,username")
            .execute()
        )

        users = users_res.data if users_res.data else []
        user_lookup = {u["id"]: u["username"] for u in users}

        # Group by artist
        grouped = {}

        for row in rows:
            artist_id = row["artist_id"]
            artist_name = row["name"]
            username = user_lookup.get(row["user_id"], f"User {row['user_id']}")

            if artist_id not in grouped:
                grouped[artist_id] = {
                    "artist_id": artist_id,
                    "artist_name": artist_name,
                    "users": []
                }

            if username not in grouped[artist_id]["users"]:
                grouped[artist_id]["users"].append(username)

        # Convert dict to list and sort by number of users descending
        result = list(grouped.values())
        result.sort(key=lambda x: len(x["users"]), reverse=True)

        # Only show first 10 artists
        return jsonify(result[:10])

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
