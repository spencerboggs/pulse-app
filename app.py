from flask import Flask, render_template, redirect, url_for, request, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from dotenv import load_dotenv
import os, re

# ============================================================
# ENVIRONMENT LOADING
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        return render_template("auth.html")

    # ===== SIGNUP =====
    @app.route("/signup", methods=["POST"])
    def signup():
        full_name = request.form["fullName"]
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]

        # Check for existing user
        existing = supabase.table("auth_users").select("*").eq("username", username).execute()
        if existing.data:
            flash("Username already taken.", "error")
            return redirect(url_for("auth"))

        # Hash password
        password_hash = generate_password_hash(password)

        # Insert into auth_users
        user_result = supabase.table("auth_users").insert({
            "username": username,
            "password_hash": password_hash
        }).execute()

        user_id = user_result.data[0]["id"]

        # Insert into profiles
        supabase.table("profiles").insert({
            "id": user_id,
            "display_name": full_name,
            "email": email
        }).execute()

        # Auto-login
        session["user_id"] = user_id
        session["username"] = username

        return redirect(url_for("home"))

    # ===== LOGIN =====
    @app.route("/login", methods=["POST"])
    def login():
        username = request.form["username"]
        password = request.form["password"]

        user_query = supabase.table("auth_users").select("*").eq("username", username).execute()
        user = user_query.data[0] if user_query.data else None

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return redirect(url_for("auth"))

        session["user_id"] = user["id"]
        session["username"] = username

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
        return render_template("profile.html", img_url=img_url, display_name=session["username"])

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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
