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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET", "SUPER_SECRET_KEY")

    def slugify(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    def pick_user_image_by_slug(slug: str) -> str:
        uploads_path = os.path.join(app.static_folder, "uploads")
        os.makedirs(uploads_path, exist_ok=True)

        exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")

        for ext in exts:
            candidate = os.path.join(uploads_path, f"{slug}{ext}")
            if os.path.exists(candidate):
                return url_for("static", filename=f"uploads/{slug}{ext}")

        images = [f for f in os.listdir(uploads_path) if f.lower().endswith(exts)]
        if images:
            latest = max(images, key=lambda f: os.path.getmtime(os.path.join(uploads_path, f)))
            return url_for("static", filename=f"uploads/{latest}")

        return url_for("static", filename="images/profile_placeholder.png")

    def get_current_user_id():
        return session.get("user_id")

    def get_full_name(user: dict) -> str:
        first = (user.get("first_name") or "").strip()
        last = (user.get("last_name") or "").strip()
        full = f"{first} {last}".strip()
        return full if full else (user.get("username") or user.get("email") or "User")

    def get_initials(name: str) -> str:
        parts = [p for p in name.split() if p]
        if not parts:
            return "U"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def get_friend_requests_for_user(user_id: int):
        rows = supabase.table("friends") \
            .select("*") \
            .eq("addressee_id", user_id) \
            .eq("status", "pending") \
            .order("created_at", desc=True) \
            .execute()

        requests_list = []

        for row in (rows.data or []):
            sender_id = row.get("requester_id")
            if sender_id is None:
                continue

            user_res = supabase.table("users") \
                .select("id, username, first_name, last_name, email") \
                .eq("id", sender_id) \
                .limit(1) \
                .execute()

            sender = user_res.data[0] if user_res.data else None
            if not sender:
                continue

            display_name = get_full_name(sender)

            requests_list.append({
                "id": int(sender.get("id")),
                "username": sender.get("username"),
                "name": display_name,
                "handle": f"@{sender.get('username')}" if sender.get("username") else "",
                "initials": get_initials(display_name),
            })

        return requests_list

    def get_friends_for_user(user_id: int):
        result = supabase.table("friends") \
            .select("*") \
            .eq("status", "accepted") \
            .or_(f"requester_id.eq.{user_id},addressee_id.eq.{user_id}") \
            .execute()

        friends_list = []

        for row in (result.data or []):
            requester_id = row.get("requester_id")
            addressee_id = row.get("addressee_id")

            other_id = addressee_id if requester_id == user_id else requester_id
            if other_id is None:
                continue

            user_res = supabase.table("users") \
                .select("id, username, first_name, last_name, email") \
                .eq("id", other_id) \
                .limit(1) \
                .execute()

            user = user_res.data[0] if user_res.data else None
            if not user:
                continue

            display_name = get_full_name(user)

            friends_list.append({
                "id": int(user.get("id")),
                "username": user.get("username"),
                "name": display_name,
                "handle": f"@{user.get('username')}" if user.get("username") else "",
                "initials": get_initials(display_name),
                "is_favorite": bool(row.get("is_favorite"))
            })

        friends_list.sort(key=lambda u: (not u["is_favorite"], (u["name"] or "").lower()))
        return friends_list

    @app.route("/")
    def index():
        return redirect(url_for("auth"))

    @app.route("/auth")
    def auth():
        return render_template("auth.html")

    @app.route("/signup", methods=["POST"])
    def signup():
        first_name = request.form["firstName"].strip()
        last_name = request.form["lastName"].strip()
        email = request.form["email"].strip()
        username = request.form["username"].strip()
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

        return redirect(url_for("home"))

    @app.route("/login", methods=["POST"])
    def login():
        identity = request.form["identity"].strip()
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

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth"))

    @app.route("/home")
    def home():
        if "user_id" not in session:
            return redirect(url_for("auth"))

        return render_template("home.html", username=session["username"])

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

    # ===== TEST ROUTE (Optional) =====
    @app.route("/test_supabase")
    def test_supabase():
        data = supabase.table("profiles").select("*").execute()
        return {"data": data.data}

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

    # ===== FRIENDS =====
    # Requires a Supabase table:
    #   create table friendships (
    #     id uuid default gen_random_uuid() primary key,
    #     user_id text not null,
    #     friend_id text not null,
    #     status text default 'accepted',
    #     created_at timestamptz default now(),
    #     unique(user_id, friend_id)
    #   );
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
                       {r["user_id"]   for r in (f2.data or [])})
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

        # Step 1 — collect accepted friend IDs (both directions)
        try:
            f1 = supabase.table("friendships").select("friend_id") \
                .eq("user_id", uid).eq("status", "accepted").execute()
            f2 = supabase.table("friendships").select("user_id") \
                .eq("friend_id", uid).eq("status", "accepted").execute()
        except Exception as e:
            return jsonify({"activity": [], "debug": f"friendships query failed: {e}"})

        friend_ids = list({r["friend_id"] for r in (f1.data or [])} |
                          {r["user_id"]   for r in (f2.data or [])})

        if not friend_ids:
            return jsonify({"activity": [], "debug": "no accepted friends found"})

        # Step 2 — get what those friends have followed
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

        # Sort by created_at descending if present, else leave as-is
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)

        # Step 3 — resolve usernames
        try:
            unique_ids = list({r["user_id"] for r in rows})
            users_res = supabase.table("users") \
                .select("id, username") \
                .in_("id", unique_ids) \
                .execute()
            id_to_username = {str(u["id"]): u["username"] for u in (users_res.data or [])}
        except Exception as e:
            id_to_username = {}

        result = [{
            "username": id_to_username.get(str(r["user_id"]), "Someone"),
            "title": r.get("title", ""),
            "badges": r.get("badges", ""),
            "created_at": r.get("created_at", "")
        } for r in rows]

        return jsonify({"activity": result})

    # ===== FOLLOW / UNFOLLOW INSIGHT ITEMS =====
    # Requires a Supabase table:
    #   create table followed_insights (
    #     id uuid default gen_random_uuid() primary key,
    #     user_id text not null,
    #     item_id text not null,
    #     title text,
    #     badges text,
    #     unique(user_id, item_id)
    #   );
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
    app.run(debug=True, host="0.0.0.0", port=5000)