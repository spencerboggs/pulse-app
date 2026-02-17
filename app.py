from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from dotenv import load_dotenv
import os, re, requests
from werkzeug.utils import secure_filename

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



    return app






app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
